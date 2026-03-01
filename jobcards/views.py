import base64
import uuid
import io
import json
from html import escape
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView, CreateView, UpdateView, ListView, View
from django.urls import reverse_lazy
from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from django.core.mail import EmailMessage

# ReportLab imports
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

from .models import User, Jobcard, JobcardItem, Company, GlobalSettings, PDFTemplateElement
from .forms import (
    UserLoginForm, CustomUserCreationForm, CompanyForm, GlobalSettingsForm,
    JobcardForm, JobcardItemFormSet, ManagerActionForm, AdminActionForm
)

# --- Helper Functions ---
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

def setup_default_template_elements():
    defaults = [
        {'element_name': 'header_logo', 'pos_x': 40, 'pos_y': 40, 'width': 120, 'height': 60, 'font_size': 0},
        {'element_name': 'company_info', 'pos_x': 200, 'pos_y': 40, 'width': 350, 'height': 60, 'font_size': 12},
        {'element_name': 'jobcard_meta', 'pos_x': 400, 'pos_y': 110, 'width': 150, 'height': 50, 'font_size': 10},
        {'element_name': 'client_details', 'pos_x': 40, 'pos_y': 110, 'width': 200, 'height': 40, 'font_size': 10},
        {'element_name': 'start_stop_times', 'pos_x': 300, 'pos_y': 150, 'width': 250, 'height': 40, 'font_size': 10},
        {'element_name': 'items_table', 'pos_x': 40, 'pos_y': 210, 'width': 515, 'height': 300, 'font_size': 10},
        {'element_name': 'manager_notes', 'pos_x': 40, 'pos_y': 530, 'width': 515, 'height': 60, 'font_size': 10},
        {'element_name': 'admin_notes', 'pos_x': 40, 'pos_y': 600, 'width': 515, 'height': 60, 'font_size': 10},
        {'element_name': 'signatures', 'pos_x': 40, 'pos_y': 680, 'width': 515, 'height': 100, 'font_size': 10},
    ]
    if not PDFTemplateElement.objects.exists():
        for d in defaults:
            PDFTemplateElement.objects.create(**d)

# --- PDF GENERATOR (Bulletproof Flowable Version) ---

def draw_background(c, doc):
    c.saveState()
    width, height = A4

    # 1. Border
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(1)
    c.rect(20, 20, width - 40, height - 40)

    # 2. Watermark
    settings_obj = GlobalSettings.objects.first()
    watermark_img = None
    if settings_obj:
        if settings_obj.watermark:
            watermark_img = settings_obj.watermark.path
        elif settings_obj.company_logo:
            watermark_img = settings_obj.company_logo.path

    if watermark_img:
        try:
            c.saveState()
            c.setFillAlpha(0.1)
            img = ImageReader(watermark_img)
            img_w, img_h = img.getSize()
            aspect = img_h / float(img_w)
            target_w = width * 0.6
            target_h = target_w * aspect
            x = (width - target_w) / 2
            y = (height - target_h) / 2
            c.drawImage(watermark_img, x, y, width=target_w, height=target_h, preserveAspectRatio=True, mask='auto')
            c.restoreState()
        except Exception as e:
            print(f"Watermark error: {e}")
            c.restoreState()

    # 3. Page Number
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawRightString(width - 30, 30, f"Page {doc.page}")

    c.restoreState()

def build_pdf_elements(jobcard, is_dummy=False):
    elements = []
    styles = getSampleStyleSheet()

    style_normal = styles['Normal']
    style_bold = ParagraphStyle('Bold', parent=style_normal, fontName='Helvetica-Bold')
    style_title = ParagraphStyle('Title', parent=style_normal, fontName='Helvetica-Bold', fontSize=14, spaceAfter=6)
    style_header_label = ParagraphStyle('HLabel', parent=style_normal, fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#444444'))
    style_header_val = ParagraphStyle('HVal', parent=style_normal, fontName='Helvetica', fontSize=10)
    style_subheading = ParagraphStyle('Subheading', parent=style_normal, fontName='Helvetica-Bold', fontSize=12, spaceAfter=10, spaceBefore=10)

    settings_obj = GlobalSettings.objects.first()

    # --- HEADER SECTION ---
    header_data = []
    logo_flowable = ""
    if settings_obj and settings_obj.company_logo:
        try:
            logo_flowable = Image(settings_obj.company_logo.path, width=120, height=50, kind='proportional')
        except: pass
    elif is_dummy:
        logo_flowable = Paragraph("<b>[LOGO]</b>", style_normal)

    c_name = settings_obj.company_name if settings_obj else "Company Name"
    if is_dummy and not settings_obj: c_name = "Acme Corp"
    c_addr = settings_obj.company_address if settings_obj else ""
    if is_dummy and not c_addr: c_addr = "123 Fake Street\nCity, Country"

    company_info = [Paragraph(escape(c_name), style_title)]
    for line in c_addr.split('\n'):
        if line.strip():
            company_info.append(Paragraph(escape(line.strip()), style_normal))

    jc_num = "JC-PREVIEW-123" if is_dummy else jobcard.jobcard_number
    jc_date = "2023-10-27" if is_dummy else jobcard.created_at.strftime('%Y-%m-%d')
    jc_stat = "APPROVED" if is_dummy else jobcard.get_status_display()
    jc_cat = "Call Out" if is_dummy else jobcard.get_category_display()

    meta_info = [
        Paragraph(f"<b>Jobcard No:</b> {escape(jc_num)}", style_normal),
        Paragraph(f"<b>Date:</b> {escape(jc_date)}", style_normal),
        Paragraph(f"<b>Status:</b> {escape(jc_stat)}", style_normal),
        Paragraph(f"<b>Category:</b> {escape(jc_cat)}", style_normal),
    ]

    header_data.append([logo_flowable, company_info, meta_info])
    header_table = Table(header_data, colWidths=[130, 220, 160])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))

    # Details Row
    c_name = "Acme Corp" if is_dummy else jobcard.client_name
    if not is_dummy:
        if jobcard.company:
            c_name = jobcard.company.name
        elif jobcard.client_name:
            c_name = jobcard.client_name
        else:
            c_name = "N/A"

    tech_name = "John Doe" if is_dummy else (jobcard.technician.get_full_name() if jobcard.technician else 'N/A')
    start_str = "2023-10-27 09:00" if is_dummy else (jobcard.time_start.strftime('%Y-%m-%d %H:%M') if jobcard.time_start else '-')
    stop_str = "2023-10-27 11:30" if is_dummy else (jobcard.time_stop.strftime('%Y-%m-%d %H:%M') if jobcard.time_stop else '-')

    details_data = [
        [Paragraph("<b>Client Name:</b>", style_header_label), Paragraph(escape(c_name), style_header_val),
         Paragraph("<b>Start Time:</b>", style_header_label), Paragraph(escape(start_str), style_header_val)],

        [Paragraph("<b>Technician:</b>", style_header_label), Paragraph(escape(tech_name), style_header_val),
         Paragraph("<b>Stop Time:</b>", style_header_label), Paragraph(escape(stop_str), style_header_val)]
    ]

    details_table = Table(details_data, colWidths=[80, 180, 80, 170])
    details_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("Job Details & Parts Used", style_subheading))

    # --- ITEMS TABLE ---
    table_data = [['Description', 'Parts Used', 'Qty', 'Person Helped']]

    if is_dummy:
        dummy_items = [
            ("Diagnosed network issue", "Cat6 Cable", "10", "Jane Smith"),
            ("Replaced Switch", "24-Port Switch", "1", "Jane Smith"),
            ("Configured VLANs", "-", "1", "IT Manager"),
        ] * 2
        table_data.extend(dummy_items)
    else:
        for item in jobcard.items.all():
            table_data.append([
                Paragraph(escape(item.description), style_normal),
                Paragraph(escape(item.parts_used), style_normal),
                escape(str(item.qty)),
                Paragraph(escape(item.person_helped), style_normal)
            ])

    items_table = Table(table_data, colWidths=[200, 160, 40, 110], repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f4f6f9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 20))

    # --- NOTES & SIGNATURES ---
    status = "INVOICED" if is_dummy else jobcard.status

    tech_notes = "Replaced parts and tested." if is_dummy else jobcard.tech_notes
    tech_sig = None if is_dummy else jobcard.tech_signature
    client_sig = None if is_dummy else jobcard.client_signature

    elements.append(Paragraph("Technician Notes:", style_bold))
    elements.append(Paragraph(escape(tech_notes) or "N/A", style_normal))
    elements.append(Spacer(1, 15))

    def build_sig_block(title, name, img_field):
        block = [Paragraph(f"<b>{escape(title)}:</b> {escape(name)}", style_normal)]
        if img_field:
            try:
                block.append(Image(img_field.path, width=120, height=40, kind='proportional'))
            except:
                block.append(Spacer(1, 40))
        else:
            block.append(Spacer(1, 40))
        return block

    tech_block = build_sig_block("Tech Sign", tech_name, tech_sig)
    client_block = build_sig_block("Client Sign", c_name, client_sig)

    sig_data = [[tech_block, client_block]]
    sig_table = Table(sig_data, colWidths=[255, 255])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOX', (0,0), (0,0), 1, colors.HexColor('#ced4da')),
        ('BOX', (1,0), (1,0), 1, colors.HexColor('#ced4da')),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))

    elements.append(KeepTogether(sig_table))
    elements.append(Spacer(1, 20))

    if status in ['APPROVED', 'INVOICED']:
        manager_notes = "Approved. Good work." if is_dummy else jobcard.manager_notes
        manager_sig = None if is_dummy else jobcard.manager_signature
        manager_name = "Boss Man" if is_dummy else jobcard.manager_name

        elements.append(Paragraph("Manager Notes:", style_bold))
        elements.append(Paragraph(escape(manager_notes) or "N/A", style_normal))
        elements.append(Spacer(1, 15))

        man_block = build_sig_block("Manager Sign", manager_name, manager_sig)
        man_table = Table([[man_block, ""]], colWidths=[255, 255])
        man_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOX', (0,0), (0,0), 1, colors.HexColor('#ced4da')),
            ('LEFTPADDING', (0,0), (0,0), 10),
            ('RIGHTPADDING', (0,0), (0,0), 10),
            ('TOPPADDING', (0,0), (0,0), 10),
            ('BOTTOMPADDING', (0,0), (0,0), 10),
        ]))
        elements.append(KeepTogether(man_table))
        elements.append(Spacer(1, 20))

    if status == 'INVOICED':
        admin_notes = "Invoiced #INV-999" if is_dummy else jobcard.admin_notes
        elements.append(Paragraph("Admin Notes:", style_bold))
        elements.append(Paragraph(escape(admin_notes) or "N/A", style_normal))

    return elements

def generate_pdf_buffer(jobcard, is_dummy=False):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=50
    )
    elements = build_pdf_elements(jobcard, is_dummy)
    doc.build(elements, onFirstPage=draw_background, onLaterPages=draw_background)
    buffer.seek(0)
    return buffer

def generate_dummy_pdf_buffer():
    return generate_pdf_buffer(None, is_dummy=True)


# --- VIEWS ---

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

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        initial['tech_name'] = user.get_full_name() or user.username
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['item_formset'] = JobcardItemFormSet(self.request.POST)
        else:
            data['item_formset'] = JobcardItemFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['item_formset']

        action = self.request.POST.get('action')

        # Strict Validation Check
        if action == 'submit':
            valid = True

            if not form.cleaned_data.get('time_stop'):
                messages.error(self.request, "You must Stop the timer before submitting.")
                valid = False

            has_items = False
            if items.is_valid():
                for item_form in items.cleaned_data:
                    if item_form and not item_form.get('DELETE', False):
                        if item_form.get('description'):
                            has_items = True
                            break
            else:
                valid = False # Formset itself is invalid

            if not has_items and valid:
                messages.error(self.request, "You must add at least one Job Detail before submitting.")
                valid = False

            if not valid:
                return self.render_to_response(self.get_context_data(form=form, items=items))

        self.object = form.save(commit=False)
        self.object.technician = self.request.user

        tech_sig = form.cleaned_data.get('tech_signature_data')
        client_sig = form.cleaned_data.get('client_signature_data')

        if tech_sig:
            self.object.tech_signature = save_signature_image(tech_sig)
        if client_sig:
            self.object.client_signature = save_signature_image(client_sig)

        if action == 'submit':
            self.object.status = Jobcard.Status.SUBMITTED

        self.object.save()

        if items.is_valid():
            items.instance = self.object
            items.save()

            if action == 'submit':
                try:
                    pdf_buffer = generate_pdf_buffer(self.object)

                    to_email = None
                    if self.object.company and self.object.company.email:
                        to_email = self.object.company.email

                    if to_email:
                        email = EmailMessage(
                            subject=f'Jobcard Submitted: {self.object.jobcard_number}',
                            body=f'Please find attached the jobcard.',
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            to=[to_email]
                        )
                        email.attach(f'{self.object.jobcard_number}.pdf', pdf_buffer.read(), 'application/pdf')
                        email.send(fail_silently=True)
                        messages.success(self.request, "Jobcard submitted and emailed!")
                    else:
                        messages.success(self.request, "Jobcard submitted successfully! (No email sent, company email missing).")
                except Exception as e:
                    messages.warning(self.request, f"Jobcard submitted but email/PDF failed: {e}")
            else:
                 messages.success(self.request, "Jobcard draft saved!")

            return redirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form, items=items))

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
            data['item_formset'] = JobcardItemFormSet(self.request.POST, instance=self.object)
        else:
            data['item_formset'] = JobcardItemFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['item_formset']

        action = self.request.POST.get('action')

        # Strict Validation Check
        if action == 'submit':
            valid = True

            if not form.cleaned_data.get('time_stop'):
                messages.error(self.request, "You must Stop the timer before submitting.")
                valid = False

            has_items = False
            if items.is_valid():
                for item_form in items.cleaned_data:
                    if item_form and not item_form.get('DELETE', False):
                        if item_form.get('description'):
                            has_items = True
                            break
            else:
                valid = False

            if not has_items and valid:
                messages.error(self.request, "You must add at least one Job Detail before submitting.")
                valid = False

            if not valid:
                return self.render_to_response(self.get_context_data(form=form, items=items))

        self.object = form.save(commit=False)

        tech_sig = form.cleaned_data.get('tech_signature_data')
        client_sig = form.cleaned_data.get('client_signature_data')

        if tech_sig:
            self.object.tech_signature = save_signature_image(tech_sig)
        if client_sig:
            self.object.client_signature = save_signature_image(client_sig)

        if action == 'submit':
            self.object.status = Jobcard.Status.SUBMITTED

        self.object.save()

        if items.is_valid():
            items.save()

            if action == 'submit':
                try:
                    pdf_buffer = generate_pdf_buffer(self.object)
                    to_email = None
                    if self.object.company and self.object.company.email:
                        to_email = self.object.company.email

                    if to_email:
                        email = EmailMessage(
                            subject=f'Jobcard Submitted: {self.object.jobcard_number}',
                            body=f'Please find attached the jobcard.',
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            to=[to_email]
                        )
                        email.attach(f'{self.object.jobcard_number}.pdf', pdf_buffer.read(), 'application/pdf')
                        email.send(fail_silently=True)
                        messages.success(self.request, "Jobcard submitted and emailed!")
                    else:
                        messages.success(self.request, "Jobcard submitted successfully! (No email sent).")
                except Exception as e:
                    messages.warning(self.request, f"Jobcard submitted but email/PDF failed: {e}")
            else:
                 messages.success(self.request, "Jobcard updated successfully!")

            return redirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form, items=items))

class JobcardAutosaveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        jobcard = get_object_or_404(Jobcard, pk=pk)
        if jobcard.technician != request.user and not request.user.is_superuser:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        form = JobcardForm(request.POST, instance=jobcard, user=request.user)
        if form.is_valid():
            jobcard = form.save(commit=False)

            tech_sig = form.cleaned_data.get('tech_signature_data')
            client_sig = form.cleaned_data.get('client_signature_data')

            if tech_sig:
                jobcard.tech_signature = save_signature_image(tech_sig)
            if client_sig:
                jobcard.client_signature = save_signature_image(client_sig)

            jobcard.save()

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

class AdminArchiveListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Jobcard
    template_name = 'jobcard_archive.html'
    context_object_name = 'archived_jobcards'
    paginate_by = 20

    def test_func(self):
        return self.request.user.is_admin_role() or self.request.user.is_superuser

    def get_queryset(self):
        qs = Jobcard.objects.filter(status=Jobcard.Status.INVOICED).order_by('-created_at')

        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(
                Q(jobcard_number__icontains=query) |
                Q(company__name__icontains=query) |
                Q(technician__username__icontains=query)
            )

        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category=category)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category_choices'] = Jobcard.Category.choices
        return context

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

class CompanyCreateAJAXView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            name = data.get('name')
            if not name:
                return JsonResponse({'success': False, 'message': 'Company name is required.'}, status=400)

            company = Company.objects.create(
                name=name,
                address=data.get('address', ''),
                contact_number=data.get('contact_number', ''),
                email=data.get('email', '')
            )
            return JsonResponse({'success': True, 'id': company.id, 'name': company.name})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

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

        try:
            buffer = generate_pdf_buffer(jobcard)
        except Exception as e:
            return HttpResponse(f"Error generating PDF: {e}", status=500)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{jobcard.jobcard_number}.pdf"'
        return response

class FormDesignerView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'form_designer.html'

    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

    def get(self, request):
        setup_default_template_elements()
        elements = PDFTemplateElement.objects.all()
        return render(request, self.template_name, {'elements': elements})

class SaveTemplateLayoutView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

    def post(self, request):
        try:
            data = json.loads(request.body)
            elements_data = data.get('elements', [])

            for item in elements_data:
                name = item.get('name')
                if name:
                    element, created = PDFTemplateElement.objects.get_or_create(element_name=name)
                    element.pos_x = float(item.get('x', 0))
                    element.pos_y = float(item.get('y', 0))
                    element.width = float(item.get('width', 100))
                    element.height = float(item.get('height', 50))
                    element.save()

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

class PreviewPDFTemplateView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_manager() or self.request.user.is_superuser

    def get(self, request):
        try:
            buffer = generate_dummy_pdf_buffer()
        except Exception as e:
            return HttpResponse(f"Error generating Preview PDF: {e}", status=500)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="jobcard_preview.pdf"'
        return response
