"""Appointment and Doctor Review Models."""
import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.accounts.models import PatientProfile, PatientDependent
from apps.facilities.models import Hospital, Clinic
from apps.doctors.models import Doctor

class AppointmentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'

class Appointment(models.Model):
    """Consultation booking linking patient care with attending doctor and facility."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Authenticated user account who booked the appointment
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='booked_appointments'
    )
    
    # Specific patient identity receiving care (Primary Patient OR Dependent Patient)
    patient_profile = models.ForeignKey(
        PatientProfile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='appointments'
    )
    dependent = models.ForeignKey(
        PatientDependent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='appointments'
    )
    
    # Doctor and facility relationships
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,
        related_name='appointments'
    )
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='appointments'
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='appointments'
    )
    
    # Historical snapshots at time of booking
    patient_name_snapshot = models.CharField(max_length=255)
    patient_phone_snapshot = models.CharField(max_length=32, blank=True)
    patient_email_snapshot = models.EmailField(blank=True)
    specialty_snapshot = models.CharField(max_length=128)
    
    # Timing and slot scheduling
    date = models.DateField(db_index=True)
    time_slot = models.CharField(max_length=32, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.CONFIRMED,
        db_index=True
    )
    notes = models.TextField(blank=True)
    
    # Cancellation audit tracking
    cancel_reason = models.TextField(blank=True)
    cancelled_by_role = models.CharField(max_length=16, blank=True)
    cancelled_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_appointments'
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetadr_appointments'
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        constraints = [
            # Authoritative partial unique index preventing duplicate active bookings
            models.UniqueConstraint(
                fields=['doctor', 'date', 'time_slot'],
                condition=models.Q(status__in=[AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING]),
                name='unique_active_doctor_slot'
            ),
            # Exclusive treated patient check: either primary patient or dependent, never both, never neither
            models.CheckConstraint(
                check=(
                    models.Q(patient_profile__isnull=False, dependent__isnull=True) |
                    models.Q(patient_profile__isnull=True, dependent__isnull=False)
                ),
                name='appointment_must_have_primary_xor_dependent_patient'
            )
        ]

    def __str__(self):
        patient_name = self.patient_name_snapshot or (self.patient_profile.user.name if self.patient_profile else (self.dependent.name if self.dependent else 'Patient'))
        return f"Apt {self.id}: {patient_name} with Dr. {self.doctor.name} on {self.date} @ {self.time_slot} ({self.status})"

class DoctorReview(models.Model):
    """Verified patient feedback and 1-5 star rating on a completed consultation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.PROTECT,
        related_name='review'
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='doctor_reviews'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetadr_doctor_reviews'
        verbose_name = 'Doctor Review'
        verbose_name_plural = 'Doctor Reviews'

    def __str__(self):
        return f"Review for Dr. {self.doctor.name}: {self.rating} stars"
