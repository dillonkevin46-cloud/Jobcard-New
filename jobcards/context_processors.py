from .models import GlobalSettings

def global_settings(request):
    settings_obj = GlobalSettings.objects.first()
    return {'global_settings': settings_obj}
