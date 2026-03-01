from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView, DashboardView, JobcardCreateView, JobcardUpdateView,
    ManagerJobcardView, AdminJobcardView, UserListView, UserCreateView,
    UserUpdateView, UserDeleteView,
    CompanyCreateView, SettingsView, JobcardPDFView, JobcardAutosaveView,
    FormDesignerView, SaveTemplateLayoutView, PreviewPDFTemplateView,
    AdminArchiveListView, CompanyCreateAJAXView, ResendJobcardEmailView
)

urlpatterns = [
    # Auth & Password Reset
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

    # Dashboard & Jobcards
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('create/', JobcardCreateView.as_view(), name='jobcard_create'),
    path('update/<int:pk>/', JobcardUpdateView.as_view(), name='jobcard_update'),
    path('autosave/<int:pk>/', JobcardAutosaveView.as_view(), name='jobcard_autosave'),
    path('pdf/<int:pk>/', JobcardPDFView.as_view(), name='jobcard_pdf'),

    # Manager
    path('manager/approve/<int:pk>/', ManagerJobcardView.as_view(), name='manager_approve'),
    path('manage/users/', UserListView.as_view(), name='user_list'),
    path('manage/users/create/', UserCreateView.as_view(), name='user_create'),
    path('manage/users/<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),
    path('manage/users/<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),
    path('manage/company/create/', CompanyCreateView.as_view(), name='company_create'),
    path('manage/company/ajax-create/', CompanyCreateAJAXView.as_view(), name='company_create_ajax'),
    path('settings/', SettingsView.as_view(), name='settings'),
    path('manage/designer/', FormDesignerView.as_view(), name='form_designer'),
    path('manage/designer/save/', SaveTemplateLayoutView.as_view(), name='save_template_layout'),
    path('manage/designer/preview/', PreviewPDFTemplateView.as_view(), name='preview_template_layout'),

    # Admin
    path('manage/invoice/<int:pk>/', AdminJobcardView.as_view(), name='admin_invoice'),
    path('manage/archive/', AdminArchiveListView.as_view(), name='admin_archive'),
    path('manage/resend-email/<int:pk>/', ResendJobcardEmailView.as_view(), name='resend_jobcard_email'),
]
