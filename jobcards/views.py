import base64
import uuid
import io
import json
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

# ReportLab imports (Canvas)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm

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
    """Initializes default PDF template elements if none exist."""
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

def generate_pdf_buffer(jobcard):
    """
    Generates a PDF using reportlab.pdfgen.canvas and PDFTemplateElement coordinates.
    """
    setup_default_template_elements() # Ensure elements exist
    elements = {e.element_name: e for e in PDFTemplateElement.objects.all()}

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4 # 595.27, 841.89 points

    # 1. Draw Border
    p.setStrokeColorRGB(0, 0, 0)
    p.setLineWidth(1)
    p.rect(20, 20, width - 40, height - 40)

    # --- GLOBAL SETTINGS ---
    settings_obj = GlobalSettings.objects.first()

    # --- LOGO ---
    if 'header_logo' in elements:
        el = elements['header_logo']
        if settings_obj and settings_obj.company_logo:
            try:
                # drawImage(image, x, y, width, height)
                # y is bottom-left of image
                rl_y = height - el.pos_y - el.height
                p.drawImage(settings_obj.company_logo.path, el.pos_x, rl_y, width=el.width, height=el.height, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Logo error: {e}")

    # --- COMPANY INFO ---
    if 'company_info' in elements:
        el = elements['company_info']
        rl_y = height - el.pos_y - el.font_size # Approximation for text baseline
        p.setFont("Helvetica-Bold", el.font_size + 2)
        p.drawString(el.pos_x, rl_y, settings_obj.company_name if settings_obj else "Company Name")

        p.setFont("Helvetica", el.font_size)
        lines = (settings_obj.company_address if settings_obj else "").split('\n')
        for i, line in enumerate(lines):
            p.drawString(el.pos_x, rl_y - ((i+1) * (el.font_size + 2)), line)

    # --- JOBCARD META (Jobcard Details) ---
    if 'jobcard_meta' in elements:
        el = elements['jobcard_meta']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica-Bold", el.font_size)
        p.drawString(el.pos_x, rl_y, f"Jobcard No: {jobcard.jobcard_number}")
        p.drawString(el.pos_x, rl_y - 12, f"Date: {jobcard.created_at.strftime('%Y-%m-%d')}")
        p.drawString(el.pos_x, rl_y - 24, f"Status: {jobcard.get_status_display()}")
        p.drawString(el.pos_x, rl_y - 36, f"Category: {jobcard.get_category_display()}")

        # Technician Name under Meta or Client Details
        p.drawString(el.pos_x, rl_y - 48, f"Tech: {jobcard.technician.get_full_name() if jobcard.technician else 'N/A'}")

    # --- CLIENT DETAILS ---
    if 'client_details' in elements:
        el = elements['client_details']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica", el.font_size)
        p.drawString(el.pos_x, rl_y, f"Client: {jobcard.company.name}")
        p.drawString(el.pos_x, rl_y - 12, f"Address: {jobcard.company.address[:50]}") # Truncate

    # --- START/STOP TIMES ---
    if 'start_stop_times' in elements:
        el = elements['start_stop_times']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica", el.font_size)
        start_str = jobcard.time_start.strftime('%Y-%m-%d %H:%M') if jobcard.time_start else '-'
        stop_str = jobcard.time_stop.strftime('%Y-%m-%d %H:%M') if jobcard.time_stop else '-'
        p.drawString(el.pos_x, rl_y, f"Start: {start_str}")
        p.drawString(el.pos_x + 120, rl_y, f"Stop: {stop_str}") # Offset stop time

    # --- ITEMS TABLE ---
    if 'items_table' in elements:
        el = elements['items_table']
        rl_y = height - el.pos_y

        # Draw Headers
        p.setFont("Helvetica-Bold", el.font_size)
        # Column widths: Description (40%), Parts (30%), Qty (10%), Person (20%)
        col1_w = el.width * 0.4
        col2_w = el.width * 0.3
        col3_w = el.width * 0.1
        col4_w = el.width * 0.2

        row_h = el.font_size + 8
        current_y = rl_y - row_h

        # Header BG
        p.setFillColorRGB(0.9, 0.9, 0.9)
        p.rect(el.pos_x, current_y, el.width, row_h, fill=1, stroke=1)
        p.setFillColorRGB(0, 0, 0)

        # Header Text
        text_y = current_y + 5
        p.drawString(el.pos_x + 5, text_y, "Description")
        p.drawString(el.pos_x + col1_w + 5, text_y, "Parts Used")
        p.drawString(el.pos_x + col1_w + col2_w + 5, text_y, "Qty")
        p.drawString(el.pos_x + col1_w + col2_w + col3_w + 5, text_y, "Person Helped")

        # Items
        p.setFont("Helvetica", el.font_size)
        for item in jobcard.items.all():
            current_y -= row_h
            if current_y < 40: # Page break safety (simple version: just stop drawing)
                break

            p.rect(el.pos_x, current_y, el.width, row_h, fill=0, stroke=1)
            # Vertical lines
            p.line(el.pos_x + col1_w, current_y, el.pos_x + col1_w, current_y + row_h)
            p.line(el.pos_x + col1_w + col2_w, current_y, el.pos_x + col1_w + col2_w, current_y + row_h)
            p.line(el.pos_x + col1_w + col2_w + col3_w, current_y, el.pos_x + col1_w + col2_w + col3_w, current_y + row_h)

            text_y = current_y + 5
            p.drawString(el.pos_x + 5, text_y, item.description[:40])
            p.drawString(el.pos_x + col1_w + 5, text_y, item.parts_used[:30])
            p.drawString(el.pos_x + col1_w + col2_w + 5, text_y, str(item.qty))
            p.drawString(el.pos_x + col1_w + col2_w + col3_w + 5, text_y, item.person_helped[:20])

    # --- MANAGER NOTES ---
    if 'manager_notes' in elements and jobcard.manager_notes:
        el = elements['manager_notes']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica-Bold", el.font_size)
        p.drawString(el.pos_x, rl_y, "Manager Notes:")
        p.setFont("Helvetica", el.font_size)
        p.drawString(el.pos_x, rl_y - 12, jobcard.manager_notes[:200]) # Simple truncate

    # --- ADMIN NOTES ---
    if 'admin_notes' in elements and jobcard.admin_notes:
        el = elements['admin_notes']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica-Bold", el.font_size)
        p.drawString(el.pos_x, rl_y, "Admin Notes:")
        p.setFont("Helvetica", el.font_size)
        p.drawString(el.pos_x, rl_y - 12, jobcard.admin_notes[:200])

    # --- SIGNATURES ---
    if 'signatures' in elements:
        el = elements['signatures']
        rl_y = height - el.pos_y - el.height

        # Draw box for signatures
        # p.rect(el.pos_x, rl_y, el.width, el.height)

        col_w = el.width / 3

        # Tech Sig
        p.drawString(el.pos_x + 5, rl_y + 5, f"Tech: {jobcard.tech_name}")
        if jobcard.tech_signature:
            try:
                p.drawImage(jobcard.tech_signature.path, el.pos_x + 10, rl_y + 20, width=col_w-20, height=el.height-30, mask='auto', preserveAspectRatio=True)
            except: pass

        # Client Sig
        p.drawString(el.pos_x + col_w + 5, rl_y + 5, f"Client: {jobcard.client_name}")
        if jobcard.client_signature:
             try:
                p.drawImage(jobcard.client_signature.path, el.pos_x + col_w + 10, rl_y + 20, width=col_w-20, height=el.height-30, mask='auto', preserveAspectRatio=True)
             except: pass

        # Manager Sig
        p.drawString(el.pos_x + (col_w*2) + 5, rl_y + 5, f"Manager: {jobcard.manager_name}")
        if jobcard.manager_signature:
             try:
                p.drawImage(jobcard.manager_signature.path, el.pos_x + (col_w*2) + 10, rl_y + 20, width=col_w-20, height=el.height-30, mask='auto', preserveAspectRatio=True)
             except: pass

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

def generate_dummy_pdf_buffer():
    """
    Generates a Dummy PDF for preview purposes using hardcoded data.
    """
    setup_default_template_elements() # Ensure elements exist
    elements = {e.element_name: e for e in PDFTemplateElement.objects.all()}

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4 # 595.27, 841.89 points

    # 1. Draw Border
    p.setStrokeColorRGB(0, 0, 0)
    p.setLineWidth(1)
    p.rect(20, 20, width - 40, height - 40)

    # --- GLOBAL SETTINGS (Dummy) ---
    settings_obj = GlobalSettings.objects.first() # Still use real settings if available for logo

    # --- LOGO ---
    if 'header_logo' in elements:
        el = elements['header_logo']
        if settings_obj and settings_obj.company_logo:
            try:
                rl_y = height - el.pos_y - el.height
                p.drawImage(settings_obj.company_logo.path, el.pos_x, rl_y, width=el.width, height=el.height, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Logo error: {e}")
        else:
             # Draw Placeholder Logo
             rl_y = height - el.pos_y - el.height
             p.rect(el.pos_x, rl_y, el.width, el.height)
             p.drawString(el.pos_x + 10, rl_y + 20, "LOGO HERE")

    # --- COMPANY INFO ---
    if 'company_info' in elements:
        el = elements['company_info']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica-Bold", el.font_size + 2)
        p.drawString(el.pos_x, rl_y, settings_obj.company_name if settings_obj else "Your Company Name")

        p.setFont("Helvetica", el.font_size)
        dummy_address = settings_obj.company_address if settings_obj else "123 Business Rd\nCity, Country\nPh: 555-0199"
        lines = dummy_address.split('\n')
        for i, line in enumerate(lines):
            p.drawString(el.pos_x, rl_y - ((i+1) * (el.font_size + 2)), line)

    # --- JOBCARD META ---
    if 'jobcard_meta' in elements:
        el = elements['jobcard_meta']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica-Bold", el.font_size)
        p.drawString(el.pos_x, rl_y, "Jobcard No: JC-PREVIEW-123")
        p.drawString(el.pos_x, rl_y - 12, "Date: 2023-10-27")
        p.drawString(el.pos_x, rl_y - 24, "Status: Approved")
        p.drawString(el.pos_x, rl_y - 36, "Category: Call Out")
        p.drawString(el.pos_x, rl_y - 48, "Tech: John Doe")

    # --- CLIENT DETAILS ---
    if 'client_details' in elements:
        el = elements['client_details']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica", el.font_size)
        p.drawString(el.pos_x, rl_y, "Client: Acme Corp")
        p.drawString(el.pos_x, rl_y - 12, "Address: 456 Client Lane, Industrial Park")

    # --- START/STOP TIMES ---
    if 'start_stop_times' in elements:
        el = elements['start_stop_times']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica", el.font_size)
        p.drawString(el.pos_x, rl_y, "Start: 2023-10-27 09:00")
        p.drawString(el.pos_x + 120, rl_y, "Stop: 2023-10-27 11:30")

    # --- ITEMS TABLE ---
    if 'items_table' in elements:
        el = elements['items_table']
        rl_y = height - el.pos_y

        # Draw Headers
        p.setFont("Helvetica-Bold", el.font_size)
        col1_w = el.width * 0.4
        col2_w = el.width * 0.3
        col3_w = el.width * 0.1
        col4_w = el.width * 0.2

        row_h = el.font_size + 8
        current_y = rl_y - row_h

        # Header BG
        p.setFillColorRGB(0.9, 0.9, 0.9)
        p.rect(el.pos_x, current_y, el.width, row_h, fill=1, stroke=1)
        p.setFillColorRGB(0, 0, 0)

        # Header Text
        text_y = current_y + 5
        p.drawString(el.pos_x + 5, text_y, "Description")
        p.drawString(el.pos_x + col1_w + 5, text_y, "Parts Used")
        p.drawString(el.pos_x + col1_w + col2_w + 5, text_y, "Qty")
        p.drawString(el.pos_x + col1_w + col2_w + col3_w + 5, text_y, "Person Helped")

        # Dummy Items
        p.setFont("Helvetica", el.font_size)
        dummy_items = [
            ("Diagnosed network issue", "Cat6 Cable", "10m", "Jane Smith"),
            ("Replaced Switch", "24-Port Switch", "1", "Jane Smith"),
            ("Configured VLANs", "-", "1", "IT Manager"),
        ]

        for item in dummy_items:
            current_y -= row_h
            if current_y < 40: break

            p.rect(el.pos_x, current_y, el.width, row_h, fill=0, stroke=1)
            # Vertical lines
            p.line(el.pos_x + col1_w, current_y, el.pos_x + col1_w, current_y + row_h)
            p.line(el.pos_x + col1_w + col2_w, current_y, el.pos_x + col1_w + col2_w, current_y + row_h)
            p.line(el.pos_x + col1_w + col2_w + col3_w, current_y, el.pos_x + col1_w + col2_w + col3_w, current_y + row_h)

            text_y = current_y + 5
            p.drawString(el.pos_x + 5, text_y, item[0])
            p.drawString(el.pos_x + col1_w + 5, text_y, item[1])
            p.drawString(el.pos_x + col1_w + col2_w + 5, text_y, item[2])
            p.drawString(el.pos_x + col1_w + col2_w + col3_w + 5, text_y, item[3])

    # --- MANAGER NOTES ---
    if 'manager_notes' in elements:
        el = elements['manager_notes']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica-Bold", el.font_size)
        p.drawString(el.pos_x, rl_y, "Manager Notes:")
        p.setFont("Helvetica", el.font_size)
        p.drawString(el.pos_x, rl_y - 12, "Approved. Good work.")

    # --- ADMIN NOTES ---
    if 'admin_notes' in elements:
        el = elements['admin_notes']
        rl_y = height - el.pos_y - el.font_size
        p.setFont("Helvetica-Bold", el.font_size)
        p.drawString(el.pos_x, rl_y, "Admin Notes:")
        p.setFont("Helvetica", el.font_size)
        p.drawString(el.pos_x, rl_y - 12, "Invoiced #INV-999")

    # --- SIGNATURES ---
    if 'signatures' in elements:
        el = elements['signatures']
        rl_y = height - el.pos_y - el.height

        col_w = el.width / 3

        # Tech Sig
        p.drawString(el.pos_x + 5, rl_y + 5, "Tech: John Doe")
        p.rect(el.pos_x + 10, rl_y + 20, col_w-20, el.height-30) # Box for sig
        p.drawString(el.pos_x + 20, rl_y + 40, "[Signature]")

        # Client Sig
        p.drawString(el.pos_x + col_w + 5, rl_y + 5, "Client: Jane Smith")
        p.rect(el.pos_x + col_w + 10, rl_y + 20, col_w-20, el.height-30)
        p.drawString(el.pos_x + col_w + 20, rl_y + 40, "[Signature]")

        # Manager Sig
        p.drawString(el.pos_x + (col_w*2) + 5, rl_y + 5, "Manager: Boss Man")
        p.rect(el.pos_x + (col_w*2) + 10, rl_y + 20, col_w-20, el.height-30)
        p.drawString(el.pos_x + (col_w*2) + 20, rl_y + 40, "[Signature]")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

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

        try:
            buffer = generate_pdf_buffer(jobcard)
        except Exception as e:
            return HttpResponse(f"Error generating PDF: {e}", status=500)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{jobcard.jobcard_number}.pdf"'
        return response

# --- FORM DESIGNER VIEWS ---

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
        response['Content-Disposition'] = 'inline; filename="jobcard_preview.pdf"' # Inline for preview
        return response
