"""Prescription Authorization and Clinical Confidentiality Permissions."""
from rest_framework import permissions
from apps.accounts.models import UserRole
from apps.appointments.models import Appointment, AppointmentStatus


def has_clinical_relationship_for_prescription(user, prescription) -> bool:
    """
    Verify whether a requesting doctor has an active, legitimate clinical relationship
    with the patient or dependent of a prescription.
    
    Invariants:
    1. Caller must have DOCTOR role with an active doctor profile.
    2. Caller's affiliated hospital or clinic facility must be Active.
    3. Caller must have an active clinical encounter (confirmed or completed appointment)
       with the same patient profile, dependent, or account holder.
    """
    if not (user and user.is_authenticated and user.role == UserRole.DOCTOR):
        return False

    doctor = getattr(user, 'doctor_profile', None)
    if not doctor:
        return False

    facility = doctor.hospital or doctor.clinic
    if not facility or getattr(facility, 'status', None) != 'Active':
        return False

    valid_statuses = [AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED]
    appointment = prescription.appointment

    # Check dependent encounter
    if appointment.dependent_id:
        if Appointment.objects.filter(
            doctor=doctor,
            dependent_id=appointment.dependent_id,
            status__in=valid_statuses
        ).exists():
            return True

    # Check primary patient profile encounter
    if appointment.patient_profile_id:
        if Appointment.objects.filter(
            doctor=doctor,
            patient_profile_id=appointment.patient_profile_id,
            status__in=valid_statuses
        ).exists():
            return True

    # Check account holder encounter
    if Appointment.objects.filter(
        doctor=doctor,
        booked_by=prescription.patient,
        status__in=valid_statuses
    ).exists():
        return True

    return False


def can_access_prescription(user, prescription) -> bool:
    """
    Object-level authorization check for accessing prescription details.
    
    Allowed actors:
    - Owning patient account holder (prescription.patient == user)
    - Issuing doctor (prescription.doctor.user == user)
    - Another clinically authorized doctor with an active relationship
    
    Disallowed actors (must receive 404):
    - Unrelated patients
    - Unrelated doctors without clinical relationship
    - Facility administrators (administrative roles must not access clinical PHI)
    - Platform administrators (system admins must not access clinical PHI)
    """
    if not (user and user.is_authenticated):
        return False

    # Owning patient / account holder
    if prescription.patient_id == user.id:
        return True

    # Issuing doctor
    if prescription.doctor.user_id == user.id:
        return True

    # Clinically authorized consulting doctor
    if has_clinical_relationship_for_prescription(user, prescription):
        return True

    return False
