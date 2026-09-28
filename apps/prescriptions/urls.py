"""Prescriptions App URL Patterns."""
from django.urls import path
from apps.prescriptions import views

app_name = 'prescriptions'

urlpatterns = [
    path('', views.PrescriptionCreateView.as_view(), name='prescription-create'),
    path('my/', views.PrescriptionMyListView.as_view(), name='prescription-my-list'),
    path('<uuid:pk>/', views.PrescriptionDetailView.as_view(), name='prescription-detail'),
    path('<uuid:pk>/cancel/', views.PrescriptionCancelView.as_view(), name='prescription-cancel'),
    path('appointment/<uuid:appointment_id>/', views.AppointmentPrescriptionView.as_view(), name='appointment-prescription'),
]
