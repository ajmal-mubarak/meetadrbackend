"""Appointments App URL Patterns."""
from django.urls import path
from apps.appointments.views import (
    AppointmentBookingView,
    PatientAppointmentListView,
    AppointmentDetailView,
    AppointmentCancelView,
    DoctorAppointmentListView,
    DoctorAppointmentStatusView,
    HospitalAdminAppointmentListView,
    HospitalAdminAppointmentCancelView,
    HospitalAdminAppointmentStatusView
)

app_name = 'appointments'

urlpatterns = [
    # Patient appointment booking & history
    path('appointments/', AppointmentBookingView.as_view(), name='appointment_booking'),
    path('appointments/my/', PatientAppointmentListView.as_view(), name='my_appointments'),
    path('appointments/<uuid:pk>/', AppointmentDetailView.as_view(), name='appointment_detail'),
    path('appointments/<uuid:pk>/cancel/', AppointmentCancelView.as_view(), name='appointment_cancel'),
    path('appointments/<uuid:pk>/complete/', DoctorAppointmentStatusView.as_view(), name='appointment_complete'),

    # Doctor consultation workflows
    path('doctor/appointments/', DoctorAppointmentListView.as_view(), name='doctor_appointments'),
    path('doctor/appointments/<uuid:pk>/status/', DoctorAppointmentStatusView.as_view(), name='doctor_appointment_status'),

    # Hospital / Clinic facility administrator workflows
    path('hospital/appointments/', HospitalAdminAppointmentListView.as_view(), name='hospital_appointments'),
    path('hospital/appointments/<uuid:pk>/cancel/', HospitalAdminAppointmentCancelView.as_view(), name='hospital_appointment_cancel'),
    path('hospital/appointments/<uuid:pk>/status/', HospitalAdminAppointmentStatusView.as_view(), name='hospital_appointment_status'),
]
