from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Company, Jobcard, JobcardItem, GlobalSettings

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role',)}),
    )

class JobcardItemInline(admin.TabularInline):
    model = JobcardItem
    extra = 1

class JobcardAdmin(admin.ModelAdmin):
    list_display = ('jobcard_number', 'company', 'technician', 'status', 'created_at')
    list_filter = ('status', 'company', 'technician', 'created_at')
    search_fields = ('jobcard_number', 'company__name', 'technician__username')
    inlines = [JobcardItemInline]
    readonly_fields = ('jobcard_number', 'created_at', 'updated_at')

class GlobalSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # Only allow adding if no instance exists
        if GlobalSettings.objects.exists():
            return False
        return True

admin.site.register(User, CustomUserAdmin)
admin.site.register(Company)
admin.site.register(Jobcard, JobcardAdmin)
admin.site.register(GlobalSettings, GlobalSettingsAdmin)
