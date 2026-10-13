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


def _format_doctor_last_name(doctor) -> str:
    raw_name = getattr(doctor, 'name', '') or 'Doctor'
    clean = raw_name.replace("Dr.", "").replace("Dr ", "").strip()
    parts = clean.split()
    if not parts:
        return "Doctor"
    if len(parts) == 1:
        return parts[0]
    # Handle compound Arabic surnames like "Al Mansoori", "Bin Rashid", "Al-Qasimi"
    if len(parts) >= 2 and parts[-2].lower() in ['al', 'el', 'bin', 'ibn', 'abu']:
        return f"{parts[-2]} {parts[-1]}"
    return parts[-1]


from django.conf import settings
from django.core.mail import send_mail

def send_booking_notification_email_to_admins(appointment) -> bool:
    """
    Sends new booking notification email to Facility Administrators and Platform Admins.
    Formats the details according to the standard MeetAdr administrative template,
    ensuring 'Location' is shown instead of 'Branch'.
    """
    facility = appointment.hospital or appointment.clinic
    facility_name = getattr(facility, 'name', '') or 'MeetAdr Medical Facility'
    location = getattr(facility, 'location', '') or getattr(appointment.doctor, 'location', '') or 'United Arab Emirates'
    
    # Format date & time nicely (e.g. August 03, 2025, 15:30)
    try:
        if hasattr(appointment.date, 'strftime'):
            formatted_date = appointment.date.strftime('%B %d, %Y')
        else:
            from datetime import datetime
            parsed_date = datetime.strptime(str(appointment.date), '%Y-%m-%d')
            formatted_date = parsed_date.strftime('%B %d, %Y')
    except Exception:
        formatted_date = str(appointment.date)
    
    time_val = appointment.time_slot or 'Standard Slot'
    date_time_str = f"{formatted_date}, {time_val}"
    
    patient_name = appointment.patient_name_snapshot or 'Patient'
    patient_phone = appointment.patient_phone_snapshot or '—'
    patient_email = appointment.patient_email_snapshot or 'N/A'
    
    subject = f"New Booking: {facility_name} - {date_time_str}"
    
    plain_message = (
        "New Booking:\n"
        f"Hospital: {facility_name}\n"
        f"Location: {location}\n"
        f"Date & Time: {date_time_str}\n"
        f"Patient Name: {patient_name}\n"
        f"Patient Contact #: {patient_phone}\n"
        f"Patient Email (Optional): {patient_email}\n\n"
        "Regards\n"
        "Team MeetAdr.com"
    )
    
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px; }}
        .booking-card {{ max-width: 520px; margin: 0 auto; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; }}
        .booking-header {{ background: #0e7490; color: #ffffff; padding: 14px 18px; font-size: 16px; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        td {{ padding: 10px 16px; border-bottom: 1px solid #e2e8f0; text-align: left; }}
        td.label {{ font-weight: bold; color: #334155; width: 42%; background: #f8fafc; }}
        td.value {{ color: #0f172a; font-weight: 500; }}
        .footer {{ padding: 14px 18px; background: #f8fafc; font-size: 13px; color: #475569; }}
      </style>
    </head>
    <body>
      <div class="booking-card">
        <div class="booking-header">New Booking:</div>
        <table>
          <tbody>
            <tr>
              <td class="label">Hospital</td>
              <td class="value">{facility_name}</td>
            </tr>
            <tr>
              <td class="label">Location</td>
              <td class="value">{location}</td>
            </tr>
            <tr>
              <td class="label">Date & Time</td>
              <td class="value">{date_time_str}</td>
            </tr>
            <tr>
              <td class="label">Patient Name</td>
              <td class="value">{patient_name}</td>
            </tr>
            <tr>
              <td class="label">Patient Contact #</td>
              <td class="value">{patient_phone}</td>
            </tr>
            <tr>
              <td class="label">Patient Email (Optional)</td>
              <td class="value">{patient_email}</td>
            </tr>
          </tbody>
        </table>
        <div class="footer">
          <strong>Regards</strong><br>
          Team MeetAdr.com
        </div>
      </div>
    </body>
    </html>
    """

    recipients = set()
    facility_admin = getattr(facility, 'admin_user', None) if facility else None
    if facility_admin and getattr(facility_admin, 'email', None):
        recipients.add(facility_admin.email.lower().strip())

    for admin_u in User.objects.filter(role=UserRole.ADMIN):
        if admin_u.email:
            recipients.add(admin_u.email.lower().strip())

    if not recipients:
        logger.info("No admin recipients found for new booking email dispatch.")
        return False

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@meetadr.com')
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=list(recipients),
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"Dispatched new booking email to admins {list(recipients)} for appointment {appointment.id}")
        return True
    except Exception as exc:
        logger.warning(f"Failed to dispatch new booking email to admins: {exc}")
        return False


def send_booking_notification_email_to_patient(appointment) -> bool:
    """
    Sends the booking request notification email to the patient with the template:
    We've received your booking request for Dr. [Last Name]. Our hospital team will call you shortly to confirm your final date and time slot.

    Regards
    Team MeetAdr.com
    """
    patient_email = getattr(appointment, 'patient_email_snapshot', None)
    if not patient_email and appointment.booked_by:
        patient_email = getattr(appointment.booked_by, 'email', None)

    if not patient_email:
        logger.info(f"No patient email found for appointment {appointment.id}, skipping patient email dispatch.")
        return False

    doc_last_name = _format_doctor_last_name(appointment.doctor)
    subject = f"Booking Request Received for Dr. {doc_last_name} | MeetAdr"

    plain_message = (
        f"We've received your booking request for Dr. {doc_last_name}. "
        "Our hospital team will call you shortly to confirm your final date and time slot.\n\n"
        "Regards\n"
        "Team MeetAdr.com\n"
    )

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Booking Request Received</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b;">
      <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #e2ebf0; border-radius: 16px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.04);">
        <div style="border-bottom: 2px solid #2da7b5; padding-bottom: 16px; margin-bottom: 24px;">
          <h2 style="margin: 0; color: #0e7490; font-size: 20px; font-weight: 800;">MeetAdr.com</h2>
        </div>
        <p style="font-size: 15px; line-height: 1.6; color: #334155; margin-bottom: 24px;">
          We've received your booking request for <strong>Dr. {doc_last_name}</strong>. Our hospital team will call you shortly to confirm your final date and time slot.
        </p>
        <div style="margin-top: 32px; padding-top: 20px; border-top: 1px solid #e2ebf0; font-size: 14px; color: #64748b;">
          <p style="margin: 0; font-weight: 600; color: #334155;">Regards</p>
          <p style="margin: 4px 0 0 0; font-weight: 700; color: #0e7490;">Team MeetAdr.com</p>
        </div>
      </div>
    </body>
    </html>
    """

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@meetadr.com')
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[patient_email.lower().strip()],
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"Dispatched patient booking request email to {patient_email} for appointment {appointment.id}")
        return True
    except Exception as exc:
        logger.warning(f"Failed to dispatch patient booking request email: {exc}")
        return False


def notify_appointment_booked(appointment):
    """
    Notifies the patient, attending doctor, facility administrator, and platform admins
    upon successful booking. Also dispatches the structured booking email to admins and patient.
    """
    doc_name = _format_doctor_name(appointment.doctor)
    doc_last_name = _format_doctor_last_name(appointment.doctor)
    facility = appointment.hospital or appointment.clinic
    facility_name = facility.name if facility else "the facility"
    location = getattr(facility, 'location', '') or getattr(appointment.doctor, 'location', '') or 'UAE'

    # 1. Patient Notification
    patient_user = appointment.booked_by
    patient_desc = (
        f"We've received your booking request for Dr. {doc_last_name}. "
        "Our hospital team will call you shortly to confirm your final date and time slot."
    )

    create_notification(
        user=patient_user,
        title="Booking Request Received",
        description=patient_desc,
        notification_type=NotificationType.APPOINTMENT,
        link="/patient/bookings"
    )

    # 1b. Patient Email Dispatch
    send_booking_notification_email_to_patient(appointment)

    # 2. Doctor Notification (if doctor profile has a linked user account)
    doctor_user = getattr(appointment.doctor, 'user', None)
    if doctor_user:
        create_notification(
            user=doctor_user,
            title="New Appointment Booked",
            description=f"New consultation booked for {appointment.date} at {appointment.time_slot}.",
            notification_type=NotificationType.APPOINTMENT,
            link="/doctor/bookings"
        )

    # 3. Facility Administrator In-App Notification
    facility_admin = getattr(facility, 'admin_user', None) if facility else None
    if facility_admin:
        create_notification(
            user=facility_admin,
            title="New Booking Received",
            description=f"New booking for Dr. {doc_name} at {facility_name} ({location}) on {appointment.date} at {appointment.time_slot}.",
            notification_type=NotificationType.APPOINTMENT,
            link="/hospital/dashboard"
        )

    # 4. Platform Superadmin In-App Notifications
    for admin_u in User.objects.filter(role=UserRole.ADMIN):
        create_notification(
            user=admin_u,
            title="New Booking Received",
            description=f"New booking at {facility_name} ({location}) for Dr. {doc_name} on {appointment.date} at {appointment.time_slot}.",
            notification_type=NotificationType.APPOINTMENT,
            link="/admin/bookings"
        )

    # 5. Dispatch Structured Booking Email to Facility Admin & Platform Admins
    send_booking_notification_email_to_admins(appointment)


def notify_appointment_confirmed(appointment):
    """
    Notifies the patient when their appointment is confirmed by the doctor or clinic.
    """
    patient_user = appointment.booked_by
    doc_name = _format_doctor_name(appointment.doctor)
    facility = appointment.hospital or appointment.clinic
    facility_name = facility.name if facility else "the medical facility"
    create_notification(
        user=patient_user,
        title="Appointment Confirmed",
        description=f"Your appointment with {doc_name} at {facility_name} for {appointment.date} at {appointment.time_slot} has been confirmed.",
        notification_type=NotificationType.APPOINTMENT,
        link="/patient/bookings"
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

    # Cancelled by facility or platform administrator -> notify patient and doctor
    elif role in ('hospital', 'clinic', 'admin'):
        create_notification(
            user=patient_user,
            title="Appointment Cancelled",
            description=f"Your appointment on {appointment.date} was cancelled by administration.",
            notification_type=NotificationType.APPOINTMENT,
            link="/patient/bookings"
        )
        if doctor_user and doctor_user != cancelled_by_user:
            create_notification(
                user=doctor_user,
                title="Appointment Cancelled",
                description=f"Consultation scheduled for {appointment.date} at {appointment.time_slot} was cancelled by administration.",
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
