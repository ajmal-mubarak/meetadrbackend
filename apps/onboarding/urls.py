"""Onboarding Public App URL Patterns."""
from django.urls import path
from apps.onboarding.views import ProviderRequestCreateView, ProviderRequestPublicStatusView

app_name = 'onboarding'

urlpatterns = [
    # Public provider application submission: POST /api/v1/provider-requests/
    path('', ProviderRequestCreateView.as_view(), name='provider_request_create'),
    # Public provider application status check: GET /api/v1/provider-requests/<uuid:pk>/
    path('<uuid:pk>/', ProviderRequestPublicStatusView.as_view(), name='provider_request_public_status'),
]
