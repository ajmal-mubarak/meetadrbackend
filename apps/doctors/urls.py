"""Doctors App URL Patterns."""
from django.urls import path
from apps.accounts.views import DoctorPatientMedicalProfileView
from apps.doctors.views import (
    DoctorListView,
    DoctorDetailView,
    DoctorAvailabilityView
)

app_name = 'doctors'

urlpatterns = [
    # Public doctor directory & search
    path('doctors/', DoctorListView.as_view(), name='doctor_list'),
    path('doctors/<uuid:pk>/', DoctorDetailView.as_view(), name='doctor_detail'),
    path('doctors/<uuid:pk>/availability/', DoctorAvailabilityView.as_view(), name='doctor_availability'),

    # Phase 3: Clinical access to patient medical profile enforced via clinical encounter check
    path('doctor/patients/<uuid:patient_id>/profile/', DoctorPatientMedicalProfileView.as_view(), name='doctor_patient_profile'),
]
