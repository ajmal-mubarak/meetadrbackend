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

app_name = 'admin_onboarding'

urlpatterns = [
    # Applications review: /api/v1/admin/requests/
    path('requests/', AdminProviderRequestListView.as_view(), name='admin_request_list'),
    path('requests/<uuid:pk>/', AdminProviderRequestDetailView.as_view(), name='admin_request_detail'),
    path('requests/<uuid:pk>/status/', AdminProviderRequestStatusView.as_view(), name='admin_request_status'),

    # Provider facilities global oversight: /api/v1/admin/providers/
    path('providers/', AdminProviderListView.as_view(), name='admin_provider_list'),
    path('providers/<uuid:pk>/status/', AdminProviderStatusView.as_view(), name='admin_provider_status'),
]
