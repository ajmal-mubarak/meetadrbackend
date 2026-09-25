"""MeetAdr URL Configuration."""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Versioned API root
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/', include('apps.facilities.urls')),
    path('api/v1/', include('apps.doctors.urls')),
    path('api/v1/', include('apps.appointments.urls')),
    path('api/v1/prescriptions/', include('apps.prescriptions.urls')),
    path('api/v1/provider-requests/', include('apps.onboarding.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    # Direct alias for provider administrator appointment operations
    path('api/hospital-admin/appointments/', include('apps.appointments.hospital_admin_urls')),
]
