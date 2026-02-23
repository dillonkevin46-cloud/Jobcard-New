from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.forms import inlineformset_factory
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
            Submit('submit', 'Login', css_class='btn-primary w-100')
        )

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Create User'))

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Save Company'))

class GlobalSettingsForm(forms.ModelForm):
    class Meta:
        model = GlobalSettings
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Save Settings'))

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
            'manager_notes', 'admin_notes'
        ]
        widgets = {
            'time_start': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'time_stop': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'manager_notes': forms.Textarea(attrs={'rows': 3}),
            'admin_notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # If user is a technician, they shouldn't edit manager/admin fields
        if user and user.is_technician():
            self.fields['manager_notes'].disabled = True
            self.fields['admin_notes'].disabled = True
            self.fields['status'].widget = forms.HiddenInput() # Tech submits via specific button logic usually, or we let them change status to SUBMITTED

        # Check existing signatures
        tech_sig_html = ""
        if self.instance.pk and self.instance.tech_signature:
             tech_sig_html = f'<div class="mb-2"><img src="{self.instance.tech_signature.url}" height="50" style="border:1px solid #ccc;"> <span class="text-muted small">Current Signature</span></div>'

        client_sig_html = ""
        if self.instance.pk and self.instance.client_signature:
             client_sig_html = f'<div class="mb-2"><img src="{self.instance.client_signature.url}" height="50" style="border:1px solid #ccc;"> <span class="text-muted small">Current Signature</span></div>'

        self.helper = FormHelper()
        self.helper.form_tag = False # We will manage the form tag in the template for the whole page including formsets
        self.helper.form_class = 'jobcard-form'
        self.helper.layout = Layout(
            Row(
                Column('company', css_class='form-group col-md-6 mb-0'),
                Column('category', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('time_start', css_class='form-group col-md-6 mb-0'),
                Column('time_stop', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
             Row(
                Column(
                    HTML("""
                        <button type="button" class="btn btn-success btn-sm mb-2" onclick="setDateTime('id_time_start')">Start Now</button>
                    """),
                    css_class='col-md-6'
                ),
                Column(
                     HTML("""
                        <button type="button" class="btn btn-danger btn-sm mb-2" onclick="setDateTime('id_time_stop')">Stop Now</button>
                    """),
                    css_class='col-md-6'
                )
            ),
            'status',
            HTML("<hr>"),
            Row(
                Column('tech_name', css_class='form-group col-md-6'),
                Column('client_name', css_class='form-group col-md-6'),
            ),
            Row(
                 Column(
                    HTML(f"""
                        <label>Technician Signature</label>
                        {tech_sig_html}
                        <div class="signature-pad-wrapper border rounded p-2 mb-2 bg-white">
                            <canvas id="tech_sig_pad" width=300 height=150></canvas>
                        </div>
                        <button type="button" class="btn btn-sm btn-secondary" onclick="clearPad('tech_sig_pad')">Clear / New</button>
                    """),
                    css_class='col-md-6'
                ),
                Column(
                    HTML(f"""
                        <label>Client Signature</label>
                        {client_sig_html}
                        <div class="signature-pad-wrapper border rounded p-2 mb-2 bg-white">
                            <canvas id="client_sig_pad" width=300 height=150></canvas>
                        </div>
                        <button type="button" class="btn btn-sm btn-secondary" onclick="clearPad('client_sig_pad')">Clear / New</button>
                    """),
                    css_class='col-md-6'
                )
            ),
            'tech_signature_data',
            'client_signature_data',
            HTML("<hr>"),
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
        self.helper.add_input(Submit('submit', 'Approve & Sign'))

        manager_sig_html = ""
        if self.instance.pk and self.instance.manager_signature:
             manager_sig_html = f'<div class="mb-2"><img src="{self.instance.manager_signature.url}" height="50" style="border:1px solid #ccc;"> <span class="text-muted small">Current Signature</span></div>'

        self.helper.layout = Layout(
            'manager_notes',
            'manager_name',
            HTML(f"""
                <label>Manager Signature</label>
                {manager_sig_html}
                <div class="signature-pad-wrapper border rounded p-2 mb-2 bg-white">
                    <canvas id="manager_sig_pad" width=300 height=150></canvas>
                </div>
                <button type="button" class="btn btn-sm btn-secondary" onclick="clearPad('manager_sig_pad')">Clear / New</button>
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
        self.helper.add_input(Submit('submit', 'Update Status / Invoice'))
