"""Domain Notification Service."""
import logging
from typing import Optional
from django.contrib.auth import get_user_model
from django.db.models import Q
from apps.accounts.models import UserRole
from apps.notifications.models import Notification, NotificationType

logger = logging.getLogger(__name__)
User = get_user_model()


def create_notification(
    user,
    title: str,
    description: str,
    notification_type: str = NotificationType.APPOINTMENT,
    link: str = ""
) -> Optional[Notification]:
    """
    Creates an in-app notification row for a specific user.
    Executed inside the active database transaction to guarantee atomicity with the business event.
    """
    if not user or not getattr(user, 'is_authenticated', False) and not getattr(user, 'id', None):
        return None

    try:
        return Notification.objects.create(
            user=user,
            title=title,
            description=description,
            notification_type=notification_type,
            link=link
        )
    except Exception as exc:
        logger.error(f"Failed to create notification for user {user.id}: {exc}")
        raise exc


def _format_doctor_name(doctor) -> str:
    name = getattr(doctor, 'name', 'Doctor')
    return name if name.startswith("Dr.") else f"Dr. {name}"


def notify_appointment_booked(appointment):
    """
    Notifies the patient/account holder and attending doctor upon successful booking.
    Does not leak PHI; masks dependent full names.
    """
    # 1. Patient Notification
    patient_user = appointment.booked_by
    doc_name = _format_doctor_name(appointment.doctor)
    if appointment.dependent:
        desc = "Your appointment for a dependent has been confirmed."
    else:
        facility = appointment.hospital or appointment.clinic
        facility_name = facility.name if facility else "the facility"
        desc = f"Your appointment with {doc_name} at {facility_name} has been confirmed."

    create_notification(
        user=patient_user,
        title="Appointment Confirmed",
        description=desc,
        notification_type=NotificationType.APPOINTMENT,
        link="/patient/bookings"
    )

    # 2. Doctor Notification (if doctor profile has a linked user account)
    doctor_user = getattr(appointment.doctor, 'user', None)
    if doctor_user:
        create_notification(
            user=doctor_user,
            title="New Appointment Booked",
            description=f"New consultation booked for {appointment.date} at {appointment.time_slot}.",
            notification_type=NotificationType.APPOINTMENT,
            link="/doctor/dashboard"
        )


def notify_appointment_cancelled(appointment, cancelled_by_user=None, reason: str = ""):
    """
    Notifies the appropriate parties when an appointment is cancelled.
    """
    doctor_user = getattr(appointment.doctor, 'user', None)
    patient_user = appointment.booked_by
    role = appointment.cancelled_by_role
    doc_name = _format_doctor_name(appointment.doctor)

    # Cancelled by patient -> notify doctor
    if role == 'patient' or (cancelled_by_user and cancelled_by_user == patient_user):
        if doctor_user and doctor_user != cancelled_by_user:
            create_notification(
                user=doctor_user,
                title="Appointment Cancelled",
                description=f"Consultation scheduled for {appointment.date} at {appointment.time_slot} was cancelled by patient.",
                notification_type=NotificationType.APPOINTMENT,
                link="/doctor/dashboard"
            )

    # Cancelled by doctor -> notify patient
    elif role == 'doctor' or (doctor_user and cancelled_by_user == doctor_user):
        create_notification(
            user=patient_user,
            title="Appointment Cancelled",
            description=f"Your appointment on {appointment.date} was cancelled by {doc_name}.",
            notification_type=NotificationType.APPOINTMENT,
            link="/patient/bookings"
        )

    # Cancelled by facility administrator -> notify patient and doctor
    elif role in ('hospital', 'clinic'):
        create_notification(
            user=patient_user,
            title="Appointment Cancelled",
            description=f"Your appointment on {appointment.date} was cancelled by the facility.",
            notification_type=NotificationType.APPOINTMENT,
            link="/patient/bookings"
        )
        if doctor_user and doctor_user != cancelled_by_user:
            create_notification(
                user=doctor_user,
                title="Appointment Cancelled",
                description=f"Consultation scheduled for {appointment.date} at {appointment.time_slot} was cancelled by facility administration.",
                notification_type=NotificationType.APPOINTMENT,
                link="/doctor/dashboard"
            )


def notify_appointment_completed(appointment):
    """
    Notifies the patient when an appointment is marked completed.
    """
    patient_user = appointment.booked_by
    doc_name = _format_doctor_name(appointment.doctor)
    create_notification(
        user=patient_user,
        title="Consultation Completed",
        description=f"Your consultation with {doc_name} has been completed. You may now share your feedback.",
        notification_type=NotificationType.APPOINTMENT,
        link="/patient/bookings"
    )


def notify_prescription_ready(prescription):
    """
    Notifies the patient that a digital prescription is ready.
    Privacy rule: Zero diagnosis, zero medication names, zero dosage.
    """
    doc_name = _format_doctor_name(prescription.doctor)
    create_notification(
        user=prescription.patient,
        title="Digital Prescription Ready",
        description=f"Prescription from {doc_name} is ready for pharmacy pickup.",
        notification_type=NotificationType.PRESCRIPTION,
        link="/patient/bookings"
    )


def notify_prescription_cancelled(prescription):
    """
    Notifies the patient that a prescription was cancelled.
    """
    doc_name = _format_doctor_name(prescription.doctor)
    create_notification(
        user=prescription.patient,
        title="Prescription Cancelled",
        description=f"A prescription from {doc_name} has been cancelled.",
        notification_type=NotificationType.PRESCRIPTION,
        link="/patient/bookings"
    )


def notify_review_submitted(review):
    """
    Notifies the attending doctor of a new verified review.
    Privacy rule: Strictly anonymous, zero patient identity, zero review comments.
    """
    doctor_user = getattr(review.doctor, 'user', None)
    if doctor_user:
        create_notification(
            user=doctor_user,
            title="New Verified Review",
            description=f"A verified patient submitted a {review.rating}-star consultation rating.",
            notification_type=NotificationType.SYSTEM,
            link="/doctor/dashboard"
        )


def notify_provider_request_submitted(provider_request):
    """
    Notifies active platform administrators of a newly submitted provider partnership application.
    """
    admin_users = User.objects.filter(
        Q(role=UserRole.ADMIN) | Q(is_staff=True) | Q(is_superuser=True),
        is_active=True
    ).distinct()

    for admin in admin_users:
        create_notification(
            user=admin,
            title="New Provider Application",
            description=f"New partnership application submitted for {provider_request.name} ({provider_request.provider_type}).",
            notification_type=NotificationType.SYSTEM,
            link="/admin/requests"
        )


def notify_facility_setup_completed(user, facility):
    """
    Sends a welcome notification to the newly activated facility administrator.
    Never exposes passwords, tokens, or credentials.
    """
    facility_name = getattr(facility, 'name', 'Your Healthcare Facility')
    create_notification(
        user=user,
        title="Welcome to MeetAdr",
        description=f"Your facility portal for {facility_name} is now active. You may now manage your doctor roster and departments.",
        notification_type=NotificationType.SYSTEM,
        link="/hospital/dashboard"
    )
