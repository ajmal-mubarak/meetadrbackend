"""Role-based and Clinical Relationship Authorization Permissions."""
from rest_framework import permissions
from apps.accounts.models import UserRole

class IsPatient(permissions.BasePermission):
    """Allows access only to authenticated users with patient role."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == UserRole.PATIENT
        )

class IsDoctor(permissions.BasePermission):
    """Allows access only to authenticated doctors."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == UserRole.DOCTOR and
            hasattr(request.user, 'doctor_profile')
        )

class IsFacilityAdmin(permissions.BasePermission):
    """Allows access only to authenticated hospital/clinic administrators."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == UserRole.HOSPITAL
        )

class IsPlatformAdmin(permissions.BasePermission):
    """Allows access only to platform superadministrators or staff."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (
                request.user.role == UserRole.ADMIN or
                request.user.is_staff or
                request.user.is_superuser
            )
        )

class IsPatientAccountHolder(permissions.BasePermission):
    """Ensures patient profile or dependent belongs directly to request.user."""
    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        # If object is PatientProfile
        if hasattr(obj, 'user'):
            return obj.user == request.user
        # If object is PatientDependent
        if hasattr(obj, 'profile'):
            return obj.profile.user == request.user
        return False

class HasClinicalRelationshipWithPatient(permissions.BasePermission):
    """
    Mandates a verified doctor-patient clinical relationship.
    
    Access to a patient's medical profile or clinical history is never granted
    merely because a user is a doctor or facility employee.
    
    Requires:
    1. Authenticated user with DOCTOR role.
    2. Active doctor facility relationship.
    3. An active clinical encounter (Appointment with status 'confirmed' or 'completed').
    """
    message = "Access denied: No active clinical relationship exists with this patient."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == UserRole.DOCTOR and
            hasattr(request.user, 'doctor_profile')
        )

    def has_object_permission(self, request, view, obj):
        from apps.appointments.models import Appointment, AppointmentStatus
        from apps.accounts.models import PatientProfile, PatientDependent
        
        doctor = getattr(request.user, 'doctor_profile', None)
        if not doctor:
            return False
            
        # Check facility active state
        facility = doctor.hospital or doctor.clinic
        if not facility or getattr(facility, 'status', None) != 'Active':
            return False

        # Determine if target object is PatientProfile or PatientDependent
        valid_statuses = [AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED]
        
        if isinstance(obj, PatientProfile):
            return Appointment.objects.filter(
                doctor=doctor,
                patient_profile=obj,
                status__in=valid_statuses
            ).exists()
            
        elif isinstance(obj, PatientDependent):
            return Appointment.objects.filter(
                doctor=doctor,
                dependent=obj,
                status__in=valid_statuses
            ).exists()
            
        return False
