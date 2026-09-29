"""Doctors App URL Patterns."""
from django.urls import path
from apps.accounts.views import DoctorPatientMedicalProfileView
from apps.doctors.views import (
    DoctorListView,
    DoctorDetailView,
    DoctorAvailabilityView,
    DoctorPublicReviewListView,
)
from apps.doctors.facility_views import (
    FacilityDoctorDetailView,
    FacilityDoctorStatusView
)
from apps.doctors.portal_views import (
    DoctorScheduleManageView,
    DoctorDashboardView,
    DoctorPatientListView,
)

app_name = 'doctors'

urlpatterns = [
    # Public doctor directory & search
    path('doctors/', DoctorListView.as_view(), name='doctor_list'),
    path('doctors/<uuid:pk>/', DoctorDetailView.as_view(), name='doctor_detail'),
    path('doctors/<uuid:pk>/availability/', DoctorAvailabilityView.as_view(), name='doctor_availability'),
    path('doctors/<uuid:pk>/reviews/', DoctorPublicReviewListView.as_view(), name='doctor_public_reviews'),

    # Phase 9: Doctor portal operations (schedule, dashboard, treated patients)
    path('doctor/schedule/', DoctorScheduleManageView.as_view(), name='doctor_schedule'),
    path('doctor/dashboard/', DoctorDashboardView.as_view(), name='doctor_dashboard'),
    path('doctor/patients/', DoctorPatientListView.as_view(), name='doctor_patients'),

    # Phase 3: Clinical access to patient medical profile enforced via clinical encounter check
    path('doctor/patients/<uuid:patient_id>/profile/', DoctorPatientMedicalProfileView.as_view(), name='doctor_patient_profile'),

    # Phase 6: Direct doctor inspection/update/status routes for facility administration
    path('doctor/<uuid:pk>/', FacilityDoctorDetailView.as_view(), name='doctor_detail_management'),
    path('doctor/<uuid:pk>/status/', FacilityDoctorStatusView.as_view(), name='doctor_status_management'),
]
