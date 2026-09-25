"""User & Patient Account Models."""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from .managers import UserManager

class UserRole(models.TextChoices):
    PATIENT = 'patient', 'Patient'
    DOCTOR = 'doctor', 'Doctor'
    HOSPITAL = 'hospital', 'Hospital/Clinic Administrator'
    ADMIN = 'admin', 'Platform Superadministrator'

class BloodGroup(models.TextChoices):
    A_POS = 'A+', 'A+'
    A_NEG = 'A-', 'A-'
    B_POS = 'B+', 'B+'
    B_NEG = 'B-', 'B-'
    AB_POS = 'AB+', 'AB+'
    AB_NEG = 'AB-', 'AB-'
    O_POS = 'O+', 'O+'
    O_NEG = 'O-', 'O-'

class RelationType(models.TextChoices):
    SPOUSE = 'Spouse', 'Spouse'
    CHILD = 'Child', 'Child'
    PARENT = 'Parent', 'Parent'
    SIBLING = 'Sibling', 'Sibling'
    OTHER = 'Other', 'Other'

class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model for MeetAdr authentication."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.PATIENT,
        db_index=True
    )
    avatar = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'meetadr_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['email', 'role']),
            models.Index(fields=['role', 'is_active']),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"

class PatientProfile(models.Model):
    """Medical & demographic profile for a primary patient account holder."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='patient_profile'
    )
    gender = models.CharField(max_length=16, blank=True)
    dob = models.DateField(null=True, blank=True)
    blood_group = models.CharField(
        max_length=8,
        choices=BloodGroup.choices,
        blank=True
    )
    emergency_contact = models.CharField(max_length=64, blank=True)
    allergies = models.TextField(blank=True)
    insurance_provider = models.CharField(max_length=128, blank=True)
    insurance_number = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetadr_patient_profiles'
        verbose_name = 'Patient Profile'
        verbose_name_plural = 'Patient Profiles'

    def __str__(self):
        return f"Profile: {self.user.name} ({self.user.email})"

class PatientDependent(models.Model):
    """Dependent family member maintaining their own medical identity under an account."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name='dependents'
    )
    name = models.CharField(max_length=255)
    relation = models.CharField(max_length=32, choices=RelationType.choices)
    gender = models.CharField(max_length=16, blank=True)
    dob = models.DateField(null=True, blank=True)
    blood_group = models.CharField(
        max_length=8,
        choices=BloodGroup.choices,
        blank=True
    )
    allergies = models.TextField(blank=True)
    medical_notes = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=64, blank=True)
    insurance_provider = models.CharField(max_length=128, blank=True)
    insurance_number = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetadr_patient_dependents'
        verbose_name = 'Patient Dependent'
        verbose_name_plural = 'Patient Dependents'

    def __str__(self):
        return f"{self.name} ({self.relation} of {self.profile.user.name})"
