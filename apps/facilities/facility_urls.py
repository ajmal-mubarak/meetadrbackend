"""Facility and Hospital Portal Administrator URL Patterns."""
from django.urls import path
from apps.facilities.facility_views import (
    FacilitySettingsView,
    FacilityDashboardView,
    FacilityDepartmentListView,
    FacilityDepartmentDetailView,
)
from apps.doctors.facility_views import (
    FacilityDoctorListCreateView,
    FacilityDoctorDetailView,
    FacilityDoctorStatusView,
)

urlpatterns = [
    # Facility operational settings
    path('settings/', FacilitySettingsView.as_view(), name='facility_settings'),
    path('my-facility/', FacilitySettingsView.as_view(), name='facility_my_facility'),

    # Facility dashboard metrics
    path('dashboard/', FacilityDashboardView.as_view(), name='facility_dashboard'),

    # Clinical departments (Hospital only)
    path('departments/', FacilityDepartmentListView.as_view(), name='facility_departments'),
    path('departments/<uuid:pk>/', FacilityDepartmentDetailView.as_view(), name='facility_department_detail'),

    # Facility doctors roster management
    path('doctors/', FacilityDoctorListCreateView.as_view(), name='facility_doctors'),
    path('doctors/<uuid:pk>/', FacilityDoctorDetailView.as_view(), name='facility_doctor_detail'),
    path('doctors/<uuid:pk>/status/', FacilityDoctorStatusView.as_view(), name='facility_doctor_status'),
]
