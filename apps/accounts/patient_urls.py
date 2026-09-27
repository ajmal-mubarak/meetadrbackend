"""Patient Profile & Dependents URL Patterns."""
from django.urls import path
from apps.accounts.views import (
    PatientProfileView,
    PatientDependentViewSet
)
from apps.appointments.views import PatientAppointmentListView

app_name = 'patients'

urlpatterns = [
    path('profile/', PatientProfileView.as_view(), name='patient_profile'),
    path('appointments/', PatientAppointmentListView.as_view(), name='patient_appointments_list'),
    path('dependents/', PatientDependentViewSet.as_view({'get': 'list', 'post': 'create'}), name='patient_dependents_list'),
    path('dependents/<uuid:pk>/', PatientDependentViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='patient_dependent_detail'),
]
