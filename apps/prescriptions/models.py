"""Clinical Prescription and Medication Models."""
import uuid
from django.db import models
from django.conf import settings
from apps.appointments.models import Appointment
from apps.doctors.models import Doctor

class PrescriptionStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    DISPENSED = 'dispensed', 'Dispensed'
    CANCELLED = 'cancelled', 'Cancelled'

class Prescription(models.Model):
    """Clinical consultation prescription issued by an attending doctor."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.PROTECT,
        related_name='prescription'
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,
        related_name='prescriptions'
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='prescriptions'
    )
    diagnosis = models.TextField()
    instructions = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=PrescriptionStatus.choices,
        default=PrescriptionStatus.ACTIVE
    )
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetadr_prescriptions'
        verbose_name = 'Prescription'
        verbose_name_plural = 'Prescriptions'

    def __str__(self):
        return f"Prescription for {self.patient.name} by Dr. {self.doctor.name} ({self.status})"

class PrescriptionMedication(models.Model):
    """Specific prescribed medication line item within a prescription."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name='medications'
    )
    medication_name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=128, help_text="e.g. 500 mg")
    frequency = models.CharField(max_length=128, help_text="e.g. Twice daily after meals")
    duration = models.CharField(max_length=128, help_text="e.g. 7 days")
    instructions = models.TextField(blank=True, help_text="Specific usage directions")

    class Meta:
        db_table = 'meetadr_prescription_medications'
        verbose_name = 'Prescription Medication'
        verbose_name_plural = 'Prescription Medications'

    def __str__(self):
        return f"{self.medication_name} ({self.dosage}) - {self.frequency}"
