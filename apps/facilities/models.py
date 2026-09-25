"""Hospital, Clinic, and Facility Department Models."""
import uuid
from django.db import models
from django.conf import settings

class FacilityStatus(models.TextChoices):
    ACTIVE = 'Active', 'Active'
    DEACTIVATED = 'Deactivated', 'Deactivated'

class Hospital(models.Model):
    """Accredited medical complex providing inpatient & multi-specialty care."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='hospital_facility'
    )
    name = models.CharField(max_length=255)
    name_ar = models.CharField(max_length=255, blank=True)
    photo = models.URLField(blank=True)
    location = models.CharField(max_length=128)
    address = models.TextField()
    address_ar = models.TextField(blank=True)
    phone = models.CharField(max_length=32)
    operating_hours = models.CharField(max_length=128)
    operating_hours_ar = models.CharField(max_length=128, blank=True)
    about = models.TextField()
    about_ar = models.TextField(blank=True)
    emergency_available = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=FacilityStatus.choices,
        default=FacilityStatus.ACTIVE,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetadr_hospitals'
        verbose_name = 'Hospital'
        verbose_name_plural = 'Hospitals'

    def __str__(self):
        return f"{self.name} ({self.status})"

class Clinic(models.Model):
    """Specialized outpatient medical center focusing on primary specialties."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='clinic_facility'
    )
    name = models.CharField(max_length=255)
    name_ar = models.CharField(max_length=255, blank=True)
    photo = models.URLField(blank=True)
    location = models.CharField(max_length=128)
    address = models.TextField()
    address_ar = models.TextField(blank=True)
    primary_specialty = models.CharField(max_length=128)
    phone = models.CharField(max_length=32)
    operating_hours = models.CharField(max_length=128)
    operating_hours_ar = models.CharField(max_length=128, blank=True)
    about = models.TextField()
    about_ar = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=FacilityStatus.choices,
        default=FacilityStatus.ACTIVE,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetadr_clinics'
        verbose_name = 'Clinic'
        verbose_name_plural = 'Clinics'

    def __str__(self):
        return f"{self.name} ({self.status})"

class FacilityDepartment(models.Model):
    """Clinical department or medical division within a hospital."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        related_name='departments'
    )
    name = models.CharField(max_length=128)
    head_of_department = models.CharField(max_length=255, blank=True)
    bed_capacity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetadr_facility_departments'
        verbose_name = 'Facility Department'
        verbose_name_plural = 'Facility Departments'

    def __str__(self):
        return f"{self.hospital.name} - {self.name}"
