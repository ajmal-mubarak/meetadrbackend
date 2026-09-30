"""Platform Administrator Provider Requests & Providers URL Patterns."""
from django.urls import path
from apps.onboarding.views import (
    AdminProviderRequestListView,
    AdminProviderRequestDetailView,
    AdminProviderRequestStatusView
)
from apps.facilities.facility_views import (
    AdminProviderListView,
    AdminProviderStatusView
)
from apps.doctors.admin_views import (
    AdminDoctorListView,
    AdminDoctorStatusView,
)
from apps.appointments.admin_views import (
    AdminBookingListView,
    AdminBookingCancelView,
    AdminReportsView,
)

app_name = 'admin_onboarding'

urlpatterns = [
    # Applications review: /api/v1/admin/requests/
    path('requests/', AdminProviderRequestListView.as_view(), name='admin_request_list'),
    path('requests/<uuid:pk>/', AdminProviderRequestDetailView.as_view(), name='admin_request_detail'),
    path('requests/<uuid:pk>/status/', AdminProviderRequestStatusView.as_view(), name='admin_request_status'),

    # Provider facilities global oversight: /api/v1/admin/providers/
    path('providers/', AdminProviderListView.as_view(), name='admin_provider_list'),
    path('providers/<uuid:pk>/status/', AdminProviderStatusView.as_view(), name='admin_provider_status'),

    # Platform-wide doctor management: /api/v1/admin/doctors/
    path('doctors/', AdminDoctorListView.as_view(), name='admin_doctor_list'),
    path('doctors/<uuid:pk>/status/', AdminDoctorStatusView.as_view(), name='admin_doctor_status'),

    # Platform-wide global bookings oversight & cancellation: /api/v1/admin/bookings/
    path('bookings/', AdminBookingListView.as_view(), name='admin_booking_list'),
    path('bookings/<uuid:pk>/cancel/', AdminBookingCancelView.as_view(), name='admin_booking_cancel'),

    # Platform-wide analytical & operational reporting: /api/v1/admin/reports/
    path('reports/', AdminReportsView.as_view(), name='admin_reports'),
    path('dashboard/', AdminReportsView.as_view(), name='admin_dashboard'),
]
