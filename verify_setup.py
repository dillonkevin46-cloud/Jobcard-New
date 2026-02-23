import os
import django
from django.core.management import call_command

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jobcard_system.settings')
django.setup()

from jobcards.models import User, Company, Jobcard, JobcardItem, GlobalSettings

def verify():
    # 1. Migrations
    print("Running migrations...")
    call_command('makemigrations', 'jobcards')
    call_command('migrate')

    # 2. Create User
    print("Creating User...")
    if not User.objects.filter(username='tech1').exists():
        user = User.objects.create_user(username='tech1', password='password123', role=User.Role.TECHNICIAN)
        print(f"User created: {user.username} - {user.role}")
    else:
        print("User already exists")
        user = User.objects.get(username='tech1')

    # 3. Create Company
    print("Creating Company...")
    company, created = Company.objects.get_or_create(
        name="Test Corp",
        defaults={
            'address': "123 Test St",
            'contact_number': "555-1234",
            'email': "test@test.com"
        }
    )
    print(f"Company: {company.name}")

    # 4. Create Jobcard
    print("Creating Jobcard...")
    jobcard = Jobcard.objects.create(
        company=company,
        technician=user
    )
    print(f"Jobcard created: {jobcard.jobcard_number}")

    # 5. Create Jobcard Item
    item = JobcardItem.objects.create(
        jobcard=jobcard,
        description="Fixed server power supply",
        qty=1
    )
    print(f"Item created: {item.description}")

    # 6. Global Settings
    if not GlobalSettings.objects.exists():
        GlobalSettings.objects.create(company_name="My IT Shop")
        print("Global settings created")

    print("Verification Successful!")

if __name__ == '__main__':
    verify()
