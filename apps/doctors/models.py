"""Doctor and Doctor Schedule Models."""
import uuid
from django.db import models
from django.conf import settings
from apps.facilities.models import Hospital, Clinic, FacilityStatus

class Doctor(models.Model):
    """Accredited medical doctor affiliated with a Hospital OR Clinic."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='doctor_profile'
    )
    name = models.CharField(max_length=255)
    name_ar = models.CharField(max_length=255, blank=True)
    photo = models.URLField(blank=True)
    specialty = models.CharField(max_length=128, db_index=True)
    special_interests = models.JSONField(default=list, blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    experience_text = models.CharField(max_length=64, blank=True)
    experience_text_ar = models.CharField(max_length=64, blank=True)
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='doctors'
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='doctors'
    )
    location = models.CharField(max_length=128)
    about = models.TextField(blank=True)
    about_ar = models.TextField(blank=True)
    education = models.CharField(max_length=255, blank=True)
    consultation_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True
    )
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    review_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=FacilityStatus.choices,
        default=FacilityStatus.ACTIVE,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetadr_doctors'
        verbose_name = 'Doctor'
        verbose_name_plural = 'Doctors'
        constraints = [
            # Doctor must belong to Hospital OR Clinic, strictly exclusive
            models.CheckConstraint(
                check=(
                    models.Q(hospital__isnull=False, clinic__isnull=True) |
                    models.Q(hospital__isnull=True, clinic__isnull=False)
                ),
                name='doctor_must_belong_to_hospital_xor_clinic'
            )
        ]

    def __str__(self):
        facility = self.hospital.name if self.hospital else (self.clinic.name if self.clinic else 'Unassigned')
        return f"Dr. {self.name} ({self.specialty} @ {facility})"

class DoctorSchedule(models.Model):
    """Practicing days and standard consultation time slot availability for a doctor."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doctor = models.OneToOneField(
        Doctor,
        on_delete=models.CASCADE,
        related_name='schedule'
    )
    available_days = models.JSONField(
        default=list,
        help_text="List of active weekdays, e.g. ['Monday', 'Tuesday', 'Wednesday']"
    )
    standard_slots = models.JSONField(
        default=list,
        help_text="List of active consultation intervals, e.g. ['09:00 - 09:30', '09:30 - 10:00']"
    )
    slot_duration_minutes = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetadr_doctor_schedules'
        verbose_name = 'Doctor Schedule'
        verbose_name_plural = 'Doctor Schedules'

    def __str__(self):
        return f"Schedule for {self.doctor.name}"
