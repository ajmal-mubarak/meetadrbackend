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
from apps.importers.bulk_import_views import (
    FacilityBulkImportDoctorsView,
)
from apps.importers.bulk_zip_views import (
    BulkDoctorZipPreviewView,
    BulkDoctorZipExecuteView,
    BulkDoctorZipStatusView,
    BulkDoctorZipTemplateDownloadView,
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
    path('doctors/import/', FacilityBulkImportDoctorsView.as_view(), name='facility_doctors_bulk_import'),
    path('doctors/import-zip/preview/', BulkDoctorZipPreviewView.as_view(), name='facility_doctors_zip_preview'),
    path('doctors/import-zip/execute/', BulkDoctorZipExecuteView.as_view(), name='facility_doctors_zip_execute'),
    path('doctors/import-zip/status/<uuid:job_id>/', BulkDoctorZipStatusView.as_view(), name='facility_doctors_zip_status'),
    path('doctors/import-zip/template/', BulkDoctorZipTemplateDownloadView.as_view(), name='facility_doctors_zip_template'),
    path('doctors/<uuid:pk>/', FacilityDoctorDetailView.as_view(), name='facility_doctor_detail'),
    path('doctors/<uuid:pk>/status/', FacilityDoctorStatusView.as_view(), name='facility_doctor_status'),
]
