import base64
import uuid
import io
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView, CreateView, UpdateView, ListView, View
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from django.core.mail import EmailMessage

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet

from .models import User, Jobcard, JobcardItem, Company, GlobalSettings
from .forms import (
    UserLoginForm, CustomUserCreationForm, CompanyForm, GlobalSettingsForm,
    JobcardForm, JobcardItemFormSet, ManagerActionForm, AdminActionForm
)

def save_signature_image(base64_data):
    if not base64_data:
        return None
    try:
        if ';base64,' in base64_data:
            format, imgstr = base64_data.split(';base64,')
            ext = format.split('/')[-1]
            filename = f"{uuid.uuid4()}.{ext}"
            return ContentFile(base64.b64decode(imgstr), name=filename)
        return None
    except Exception as e:
        print(f"Error saving signature: {e}")
        return None

def generate_pdf_buffer(jobcard):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    # Header
    settings_obj = GlobalSettings.objects.first()
    if settings_obj and settings_obj.company_logo:
        try:
            logo_path = settings_obj.company_logo.path
            im = Image(logo_path, width=100, height=50)
            elements.append(im)
        except Exception:
            pass

    if settings_obj:
            elements.append(Paragraph(settings_obj.company_name, styles['Title']))
            elements.append(Paragraph(settings_obj.company_address, styles['Normal']))
            elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"Jobcard: {jobcard.jobcard_number}", styles['Heading2']))
    elements.append(Paragraph(f"Company: {jobcard.company.name}", styles['Normal']))
    elements.append(Paragraph(f"Technician: {jobcard.technician.get_full_name() if jobcard.technician else 'N/A'}", styles['Normal']))
    elements.append(Paragraph(f"Date: {jobcard.created_at.strftime('%Y-%m-%d')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Items Table
    data = [['Description', 'Parts', 'Qty', 'Person Helped']]
    for item in jobcard.items.all():
        data.append([item.description, item.parts_used, str(item.qty), item.person_helped])

    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 24))

    # Signatures
    sig_data = [['Technician', 'Client', 'Manager']]

    def get_sig_img(sig_field):
        if sig_field:
            try:
                return Image(sig_field.path, width=100, height=50)
            except:
                return "Error loading image"
        return "Not Signed"

    sig_row = [
        get_sig_img(jobcard.tech_signature),
        get_sig_img(jobcard.client_signature),
        get_sig_img(jobcard.manager_signature)
    ]
    sig_data.append(sig_row)

    sig_data.append([jobcard.tech_name, jobcard.client_name, jobcard.manager_name])

    sig_table = Table(sig_data)
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

class CustomLoginView(LoginView):
    authentication_form = UserLoginForm
    template_name = 'registration/login.html'

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if user.is_technician():
            context['active_jobcards'] = Jobcard.objects.filter(technician=user, status__in=[Jobcard.Status.DRAFT, Jobcard.Status.SUBMITTED])
            context['archived_jobcards'] = Jobcard.objects.filter(technician=user).exclude(status__in=[Jobcard.Status.DRAFT, Jobcard.Status.SUBMITTED])
        elif user.is_manager():
            context['pending_approval'] = Jobcard.objects.filter(status=Jobcard.Status.SUBMITTED)
            context['approved_jobcards'] = Jobcard.objects.filter(status=Jobcard.Status.APPROVED)
        elif user.is_admin_role() or user.is_custom_superuser():
             context['ready_for_invoice'] = Jobcard.objects.filter(status=Jobcard.Status.APPROVED)
             context['invoiced_jobcards'] = Jobcard.objects.filter(status=Jobcard.Status.INVOICED)

        return context

class JobcardCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Jobcard
    form_class = JobcardForm
    template_name = 'jobcard_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.is_technician() or self.request.user.is_superuser

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = JobcardItemFormSet(self.request.POST)
        else:
            data['items'] = JobcardItemFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        self.object = form.save(commit=False)
        self.object.technician = self.request.user

        # Handle Signatures
        tech_sig = form.cleaned_data.get('tech_signature_data')
        client_sig = form.cleaned_data.get('client_signature_data')

        if tech_sig:
            self.object.tech_signature = save_signature_image(tech_sig)
        if client_sig:
            self.object.client_signature = save_signature_image(client_sig)

        # Determine action
        action = self.request.POST.get('action')
        if action == 'submit':
            self.object.status = Jobcard.Status.SUBMITTED

        self.object.save()

        if items.is_valid():
            items.instance = self.object
            items.save()

            if action == 'submit':
                # Email Logic
                try:
                    pdf_buffer = generate_pdf_buffer(self.object)
                    email = EmailMessage(
                        subject=f'Jobcard Submitted: {self.object.jobcard_number}',
                        body=f'Please find attached the jobcard for {self.object.company.name}.',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[self.object.company.email]
                    )
                    email.attach(f'{self.object.jobcard_number}.pdf', pdf_buffer.read(), 'application/pdf')
                    email.send(fail_silently=True)
                    messages.success(self.request, "Jobcard submitted and emailed!")
                except Exception as e:
                    messages.warning(self.request, f"Jobcard submitted but email failed: {e}")
            else:
                 messages.success(self.request, "Jobcard draft saved!")

            return redirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form))

class JobcardUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Jobcard
    form_class = JobcardForm
    template_name = 'jobcard_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        obj = self.get_object()
        if self.request.user.is_technician():
             return obj.technician == self.request.user and obj.status == Jobcard.Status.DRAFT
        return False

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = JobcardItemFormSet(self.request.POST, instance=self.object)
        else:
            data['items'] = JobcardItemFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        self.object = form.save(commit=False)

        tech_sig = form.cleaned_data.get('tech_signature_data')
        client_sig = form.cleaned_data.get('client_signature_data')

        if tech_sig:
            self.object.tech_signature = save_signature_image(tech_sig)
        if client_sig:
            self.object.client_signature = save_signature_image(client_sig)

        action = self.request.POST.get('action')
        if action == 'submit':
            self.object.status = Jobcard.Status.SUBMITTED

        self.object.save()

        if items.is_valid():
            items.save()

            if action == 'submit':
                 # Email Logic
                try:
                    pdf_buffer = generate_pdf_buffer(self.object)
                    email = EmailMessage(
                        subject=f'Jobcard Submitted: {self.object.jobcard_number}',
                        body=f'Please find attached the jobcard for {self.object.company.name}.',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[self.object.company.email]
                    )
                    email.attach(f'{self.object.jobcard_number}.pdf', pdf_buffer.read(), 'application/pdf')
                    email.send(fail_silently=True)
                    messages.success(self.request, "Jobcard submitted and emailed!")
                except Exception as e:
                    messages.warning(self.request, f"Jobcard submitted but email failed: {e}")
            else:
                 messages.success(self.request, "Jobcard updated successfully!")

            return redirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form))

class JobcardAutosaveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        jobcard = get_object_or_404(Jobcard, pk=pk)
        if jobcard.technician != request.user and not request.user.is_superuser:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        # Simple autosave for basic fields
        # Note: Handling formsets via simple autosave is complex.
        # We will focus on main fields: manager_notes, tech_name, etc.
        # Ideally we use the form to validate.

        form = JobcardForm(request.POST, instance=jobcard, user=request.user)
        if form.is_valid():
            jobcard = form.save(commit=False)

            tech_sig = form.cleaned_data.get('tech_signature_data')
            client_sig = form.cleaned_data.get('client_signature_data')

            if tech_sig:
                jobcard.tech_signature = save_signature_image(tech_sig)
            if client_sig:
                jobcard.client_signature = save_signature_image(client_sig)

            # Don't save status on autosave
            jobcard.save()

            # Handle Formset Autosave
            items = JobcardItemFormSet(request.POST, instance=jobcard)
            if items.is_valid():
                items.save()

            return JsonResponse({'status': 'saved'})
        return JsonResponse({'error': form.errors}, status=400)

class ManagerJobcardView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Jobcard
    form_class = ManagerActionForm
    template_name = 'jobcard_manager.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

    def form_valid(self, form):
        self.object = form.save(commit=False)
        manager_sig = form.cleaned_data.get('manager_signature_data')
        if manager_sig:
             self.object.manager_signature = save_signature_image(manager_sig)

        if 'approve' in self.request.POST:
            self.object.status = Jobcard.Status.APPROVED

        self.object.save()
        messages.success(self.request, "Jobcard reviewed successfully!")
        return redirect(self.success_url)

class AdminJobcardView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Jobcard
    form_class = AdminActionForm
    template_name = 'jobcard_admin.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.is_admin_role() or self.request.user.is_superuser

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.status = Jobcard.Status.INVOICED
        self.object.admin_capture_name = self.request.user.get_full_name() or self.request.user.username
        self.object.admin_capture_date = timezone.now()
        self.object.save()
        messages.success(self.request, "Jobcard marked as Invoiced!")
        return redirect(self.success_url)

class UserListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = User
    template_name = 'user_list.html'

    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'user_form.html'
    success_url = reverse_lazy('user_list')

    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

class CompanyCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = 'company_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

class SettingsView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'settings_form.html'

    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

    def get(self, request):
        settings_obj = GlobalSettings.objects.first()
        form = GlobalSettingsForm(instance=settings_obj)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        settings_obj = GlobalSettings.objects.first()
        form = GlobalSettingsForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated.")
            return redirect('dashboard')
        return render(request, self.template_name, {'form': form})

class JobcardPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        jobcard = get_object_or_404(Jobcard, pk=pk)

        buffer = generate_pdf_buffer(jobcard)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{jobcard.jobcard_number}.pdf"'
        return response
