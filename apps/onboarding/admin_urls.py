"""Platform Administrator Provider Requests & Providers URL Patterns."""
from django.urls import path
from apps.onboarding.views import (
    AdminProviderRequestListView,
    AdminProviderRequestDetailView,
    AdminProviderRequestStatusView,
    AdminResendInvitationView,
)
from apps.facilities.facility_views import (
    AdminProviderListView,
    AdminProviderStatusView,
    AdminProviderDetailView,
    AdminProviderBulkActionView,
)
from apps.doctors.admin_views import (
    AdminDoctorListView,
    AdminDoctorDetailView,
    AdminDoctorStatusView,
    AdminDoctorBulkActionView,
)
from apps.appointments.admin_views import (
    AdminBookingListView,
    AdminBookingCancelView,
    AdminReportsView,
    AdminPatientListView,
    AdminPatientDetailView,
)
from apps.importers.bulk_import_views import (
    AdminBulkImportDoctorsView,
    AdminBulkImportHospitalsView,
    DownloadTemplateView,
)

app_name = 'admin_onboarding'

urlpatterns = [
    # Applications review: /api/v1/admin/requests/
    path('requests/', AdminProviderRequestListView.as_view(), name='admin_request_list'),
    path('requests/<uuid:pk>/', AdminProviderRequestDetailView.as_view(), name='admin_request_detail'),
    path('requests/<uuid:pk>/status/', AdminProviderRequestStatusView.as_view(), name='admin_request_status'),
    path('requests/<uuid:pk>/resend-invitation/', AdminResendInvitationView.as_view(), name='admin_request_resend_invitation'),

    # Provider facilities global oversight: /api/v1/admin/providers/
    path('providers/', AdminProviderListView.as_view(), name='admin_provider_list'),
    path('providers/bulk-action/', AdminProviderBulkActionView.as_view(), name='admin_provider_bulk_action'),
    path('providers/<uuid:pk>/', AdminProviderDetailView.as_view(), name='admin_provider_detail'),
    path('providers/<uuid:pk>/status/', AdminProviderStatusView.as_view(), name='admin_provider_status'),

    # Platform-wide doctor management: /api/v1/admin/doctors/
    path('doctors/', AdminDoctorListView.as_view(), name='admin_doctor_list'),
    path('doctors/bulk-action/', AdminDoctorBulkActionView.as_view(), name='admin_doctor_bulk_action'),
    path('doctors/<uuid:pk>/', AdminDoctorDetailView.as_view(), name='admin_doctor_detail'),
    path('doctors/<uuid:pk>/status/', AdminDoctorStatusView.as_view(), name='admin_doctor_status'),

    # Excel / CSV Bulk Importers & Blank Templates: /api/v1/admin/import/
    path('import/doctors/', AdminBulkImportDoctorsView.as_view(), name='admin_import_doctors'),
    path('import/hospitals/', AdminBulkImportHospitalsView.as_view(), name='admin_import_hospitals'),
    path('import/template/<str:target>/', DownloadTemplateView.as_view(), name='admin_import_template'),

    # Platform-wide patient management: /api/v1/admin/patients/
    path('patients/', AdminPatientListView.as_view(), name='admin_patient_list'),
    path('patients/<uuid:pk>/', AdminPatientDetailView.as_view(), name='admin_patient_detail'),

    # Platform-wide global bookings oversight & cancellation: /api/v1/admin/bookings/
    path('bookings/', AdminBookingListView.as_view(), name='admin_booking_list'),
    path('bookings/<uuid:pk>/cancel/', AdminBookingCancelView.as_view(), name='admin_booking_cancel'),

    # Platform-wide analytical & operational reporting: /api/v1/admin/reports/
    path('reports/', AdminReportsView.as_view(), name='admin_reports'),
    path('dashboard/', AdminReportsView.as_view(), name='admin_dashboard'),
]
