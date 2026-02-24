from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView, DashboardView, JobcardCreateView, JobcardUpdateView,
    ManagerJobcardView, AdminJobcardView, UserListView, UserCreateView,
    CompanyCreateView, SettingsView, JobcardPDFView, JobcardAutosaveView,
    FormDesignerView, SaveTemplateLayoutView
)

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('create/', JobcardCreateView.as_view(), name='jobcard_create'),
    path('update/<int:pk>/', JobcardUpdateView.as_view(), name='jobcard_update'),
    path('autosave/<int:pk>/', JobcardAutosaveView.as_view(), name='jobcard_autosave'),
    path('manager/approve/<int:pk>/', ManagerJobcardView.as_view(), name='manager_approve'),
    path('admin/invoice/<int:pk>/', AdminJobcardView.as_view(), name='admin_invoice'),
    path('admin/users/', UserListView.as_view(), name='user_list'),
    path('admin/users/create/', UserCreateView.as_view(), name='user_create'),
    path('admin/company/create/', CompanyCreateView.as_view(), name='company_create'),
    path('settings/', SettingsView.as_view(), name='settings'),
    path('pdf/<int:pk>/', JobcardPDFView.as_view(), name='jobcard_pdf'),
    path('manager/designer/', FormDesignerView.as_view(), name='form_designer'),
    path('manager/designer/save/', SaveTemplateLayoutView.as_view(), name='save_template_layout'),
]
