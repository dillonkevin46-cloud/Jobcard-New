from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field, HTML, Div
from .models import User, Jobcard, JobcardItem, Company, GlobalSettings

class UserLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            'username',
            'password',
            Submit('submit', 'Log In', css_class='btn-primary w-100 mt-2 rounded-pill')
        )

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Create User', css_class='btn-primary w-100'))

class ManagerUserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Save Changes', css_class='btn-primary w-100'))

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Save Company', css_class='btn-primary w-100'))

class GlobalSettingsForm(forms.ModelForm):
    class Meta:
        model = GlobalSettings
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Save Settings', css_class='btn-primary w-100'))

class JobcardForm(forms.ModelForm):
    # Hidden fields to store Base64 signature data
    tech_signature_data = forms.CharField(widget=forms.HiddenInput(), required=False)
    client_signature_data = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Jobcard
        fields = [
            'company', 'category', 'status',
            'time_start', 'time_stop',
            'tech_name', 'client_name',
            'tech_notes', 'manager_notes', 'admin_notes'
        ]
        widgets = {
            'time_start': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'time_stop': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'tech_notes': forms.Textarea(attrs={'rows': 3}),
            'manager_notes': forms.Textarea(attrs={'rows': 3}),
            'admin_notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()

        company = cleaned_data.get("company")
        client_name = cleaned_data.get("client_name")

        if self.data.get('action') == 'submit':
            if not company and not client_name:
                raise ValidationError("You must select a Company or manually type a Client Name to submit.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user and user.is_technician():
            self.fields['manager_notes'].disabled = True
            self.fields['admin_notes'].disabled = True
            self.fields['status'].widget = forms.HiddenInput()

        tech_sig_html = ""
        if self.instance.pk and self.instance.tech_signature:
             tech_sig_html = f'<div class="mb-2"><img src="{self.instance.tech_signature.url}" height="50" style="border:1px solid #ccc; border-radius: 4px;"> <span class="text-muted small ms-2">Current Signature</span></div>'

        client_sig_html = ""
        if self.instance.pk and self.instance.client_signature:
             client_sig_html = f'<div class="mb-2"><img src="{self.instance.client_signature.url}" height="50" style="border:1px solid #ccc; border-radius: 4px;"> <span class="text-muted small ms-2">Current Signature</span></div>'

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_class = 'jobcard-form'
        self.helper.layout = Layout(
            Row(
                Column(
                    HTML("""
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <label for="id_company" class="form-label mb-0 fw-semibold text-secondary small">COMPANY</label>
                            <button type="button" class="btn btn-sm btn-light p-0 px-2 border" data-bs-toggle="modal" data-bs-target="#createCompanyModal" style="font-size: 0.75rem;"><i class="bi bi-plus"></i> New</button>
                        </div>
                    """),
                    Field('company'),
                    css_class='form-group col-md-6 mb-3'
                ),
                Column('category', css_class='form-group col-md-6 mb-3'),
                css_class='form-row'
            ),
            Row(
                Column(
                    Row(
                        Column('time_start', css_class='col-sm-8 mb-2'),
                        Column(HTML("""<button type="button" class="btn btn-success btn-sm w-100 mt-md-4 shadow-sm" onclick="setDateTime('id_time_start')"><i class="bi bi-play-circle me-1"></i>Start</button>"""), css_class='col-sm-4'),
                        css_class='align-items-start'
                    ),
                    css_class='form-group col-md-6 mb-3'
                ),
                Column(
                     Row(
                        Column('time_stop', css_class='col-sm-8 mb-2'),
                        Column(HTML("""<button type="button" class="btn btn-danger btn-sm w-100 mt-md-4 shadow-sm" onclick="setDateTime('id_time_stop')"><i class="bi bi-stop-circle me-1"></i>Stop</button>"""), css_class='col-sm-4'),
                        css_class='align-items-start'
                    ),
                    css_class='form-group col-md-6 mb-3'
                ),
                css_class='form-row'
            ),
            'status',
            HTML("<hr class='my-4 border-secondary opacity-25' id='tech-notes-divider'>"),
            'tech_notes',
            HTML("<hr class='my-4 border-secondary opacity-25'>"),
            Row(
                Column('tech_name', css_class='form-group col-md-6 mb-3'),
                Column('client_name', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                 Column(
                    HTML(f"""
                        <label class="form-label fw-bold text-secondary">Technician Signature</label>
                        {tech_sig_html}
                        <div class="signature-pad-wrapper bg-white shadow-sm border border-primary rounded-3 p-1 mb-2 position-relative">
                            <canvas id="tech_sig_pad" width=300 height=150 style="width: 100%; height: 150px; touch-action: none; cursor: crosshair;"></canvas>
                            <button type="button" class="btn btn-sm btn-light border position-absolute top-0 end-0 m-2 rounded-circle" onclick="clearPad('tech_sig_pad')" title="Clear"><i class="bi bi-eraser"></i></button>
                        </div>
                    """),
                    css_class='col-md-6 mb-4 mb-md-0'
                ),
                Column(
                    HTML(f"""
                        <label class="form-label fw-bold text-secondary">Client Signature</label>
                        {client_sig_html}
                        <div class="signature-pad-wrapper bg-white shadow-sm border border-primary rounded-3 p-1 mb-2 position-relative">
                            <canvas id="client_sig_pad" width=300 height=150 style="width: 100%; height: 150px; touch-action: none; cursor: crosshair;"></canvas>
                             <button type="button" class="btn btn-sm btn-light border position-absolute top-0 end-0 m-2 rounded-circle" onclick="clearPad('client_sig_pad')" title="Clear"><i class="bi bi-eraser"></i></button>
                        </div>
                    """),
                    css_class='col-md-6'
                )
            ),
            'tech_signature_data',
            'client_signature_data',
            HTML("<hr class='my-4 border-secondary opacity-25'>"),
            'manager_notes',
            'admin_notes',
        )

JobcardItemFormSet = inlineformset_factory(
    Jobcard, JobcardItem,
    fields=['description', 'parts_used', 'qty', 'person_helped'],
    extra=1,
    can_delete=True
)

class ManagerActionForm(forms.ModelForm):
    manager_signature_data = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Jobcard
        fields = ['manager_name', 'manager_notes', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_id = 'managerActionForm'
        self.helper.add_input(Submit('submit', 'Approve & Sign', css_class='btn-success btn-lg w-100 mt-3 rounded-pill shadow-sm'))

        manager_sig_html = ""
        if self.instance.pk and self.instance.manager_signature:
             manager_sig_html = f'<div class="mb-2"><img src="{self.instance.manager_signature.url}" height="50" style="border:1px solid #ccc; border-radius: 4px;"> <span class="text-muted small ms-2">Current Signature</span></div>'

        self.helper.layout = Layout(
            'manager_notes',
            'manager_name',
            HTML(f"""
                <label class="form-label fw-bold text-secondary mt-3">Manager Signature</label>
                {manager_sig_html}
                <div class="signature-pad-wrapper bg-white shadow-sm border border-success rounded-3 p-1 mb-2 position-relative">
                    <canvas id="manager_sig_pad" width=300 height=150 style="width: 100%; height: 150px; touch-action: none; cursor: crosshair;"></canvas>
                    <button type="button" class="btn btn-sm btn-light border position-absolute top-0 end-0 m-2 rounded-circle" onclick="clearPad('manager_sig_pad')" title="Clear"><i class="bi bi-eraser"></i></button>
                </div>
            """),
            'manager_signature_data',
            'status'
        )

class AdminActionForm(forms.ModelForm):
    class Meta:
        model = Jobcard
        fields = ['admin_notes', 'admin_capture_name', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Update Status / Invoice', css_class='btn-primary btn-lg w-100 rounded-pill shadow-sm'))
