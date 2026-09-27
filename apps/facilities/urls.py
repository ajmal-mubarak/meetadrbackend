"""Facilities and Discovery URL Patterns."""
from django.urls import path
from apps.facilities.views import (
    HospitalListView,
    HospitalDetailView,
    ClinicListView,
    ClinicDetailView,
    SpecialtyListView,
    ConditionListView,
    ConditionDetailView
)

app_name = 'facilities'

urlpatterns = [
    # Hospitals
    path('hospitals/', HospitalListView.as_view(), name='hospital_list'),
    path('hospitals/<uuid:pk>/', HospitalDetailView.as_view(), name='hospital_detail'),

    # Clinics
    path('clinics/', ClinicListView.as_view(), name='clinic_list'),
    path('clinics/<uuid:pk>/', ClinicDetailView.as_view(), name='clinic_detail'),

    # Specialties
    path('specialties/', SpecialtyListView.as_view(), name='specialty_list'),

    # Health Conditions Directory
    path('conditions/', ConditionListView.as_view(), name='condition_list'),
    path('conditions/<str:condition_id>/', ConditionDetailView.as_view(), name='condition_detail'),
]
