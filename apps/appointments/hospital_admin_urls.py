"""Hospital/Clinic Administrator Appointment URL Patterns."""
from django.urls import path
from apps.appointments.views import HospitalAdminAppointmentCancelView

app_name = 'hospital_admin_appointments'

urlpatterns = [
    # POST /api/hospital-admin/appointments/{pk}/cancel/
    path('<uuid:pk>/cancel/', HospitalAdminAppointmentCancelView.as_view(), name='hospital_admin_cancel'),
]
