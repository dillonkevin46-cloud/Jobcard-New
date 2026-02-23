from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid

class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERUSER = 'SUPERUSER', 'Superuser'
        TECHNICIAN = 'TECHNICIAN', 'Technician'
        MANAGER = 'MANAGER', 'Manager'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TECHNICIAN)

    def is_technician(self):
        return self.role == self.Role.TECHNICIAN

    def is_manager(self):
        return self.role == self.Role.MANAGER

    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    def is_custom_superuser(self):
        return self.role == self.Role.SUPERUSER

class Company(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField()
    contact_number = models.CharField(max_length=50)
    email = models.EmailField()

    class Meta:
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name

class GlobalSettings(models.Model):
    company_name = models.CharField(max_length=255, default="My Company")
    company_logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)
    company_address = models.TextField(blank=True)
    company_contact = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = "Global Settings"

    def save(self, *args, **kwargs):
        if not self.pk and GlobalSettings.objects.exists():
            # Enforce singleton pattern
            return
        return super().save(*args, **kwargs)

    def __str__(self):
        return "Global Settings"

class Jobcard(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Submitted'
        APPROVED = 'APPROVED', 'Approved'
        INVOICED = 'INVOICED', 'Invoiced'

    class Category(models.TextChoices):
        INTERNAL = 'INTERNAL', 'Internal'
        CALL_OUT = 'CALL_OUT', 'Call Out'
        BACKUPS = 'BACKUPS', 'Backups'
        REMOTE = 'REMOTE', 'Remote'

    jobcard_number = models.CharField(max_length=20, unique=True, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    technician = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='jobcards')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.CALL_OUT)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    time_start = models.DateTimeField(null=True, blank=True)
    time_stop = models.DateTimeField(null=True, blank=True)

    # Signatures - Storing as ImageFields
    tech_signature = models.ImageField(upload_to='signatures/tech/', null=True, blank=True)
    client_signature = models.ImageField(upload_to='signatures/client/', null=True, blank=True)
    manager_signature = models.ImageField(upload_to='signatures/manager/', null=True, blank=True)

    # Names for signatures
    tech_name = models.CharField(max_length=100, blank=True)
    client_name = models.CharField(max_length=100, blank=True)
    manager_name = models.CharField(max_length=100, blank=True)

    manager_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)

    admin_capture_name = models.CharField(max_length=100, blank=True)
    admin_capture_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.jobcard_number:
             self.jobcard_number = f"JC-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.jobcard_number} - {self.company.name}"

class JobcardItem(models.Model):
    jobcard = models.ForeignKey(Jobcard, related_name='items', on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    parts_used = models.CharField(max_length=255, blank=True)
    qty = models.IntegerField(default=1)
    person_helped = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.description} ({self.qty})"
