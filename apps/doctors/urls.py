"""Doctors App URL Patterns."""
from django.urls import path
from apps.accounts.views import DoctorPatientMedicalProfileView

app_name = 'doctors'

urlpatterns = [
    # Clinical access to patient medical profile enforced via clinical encounter check
    path('doctor/patients/<uuid:patient_id>/profile/', DoctorPatientMedicalProfileView.as_view(), name='doctor_patient_profile'),
]
