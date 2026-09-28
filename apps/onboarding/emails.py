"""Email dispatch utilities for provider onboarding invitations."""
import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

def send_provider_invitation_email(user, facility, raw_token: str) -> bool:
    """
    Dispatches a single-use setup link to the approved facility administrator.
    
    Security Rules:
    - Never log raw_token in audit logs or unencrypted persistent storage.
    - Setup token is passed only in the destination email body link.
    - If email delivery fails (e.g. SMTP unavailable in local dev), log safely without leaking token.
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    setup_link = f"{frontend_url}/provider-setup?token={raw_token}"
    facility_name = getattr(facility, 'name', 'Your Healthcare Facility')
    
    subject = f"MeetAdr Provider Partnership: Complete Your Account Setup for {facility_name}"
    message = (
        f"Dear {user.name},\n\n"
        f"Congratulations! Your application for {facility_name} has been approved by the MeetAdr Administration.\n\n"
        f"To activate your facility administrator portal and configure your doctor roster, "
        f"please complete your account setup using the secure link below:\n\n"
        f"{setup_link}\n\n"
        f"Note: This single-use setup invitation expires in 72 hours.\n\n"
        f"If you did not apply for a partnership on MeetAdr, please ignore this email or contact support.\n\n"
        f"Best regards,\n"
        f"The MeetAdr Healthcare Team\n"
        f"https://meetadr.com"
    )
    
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@meetadr.com')
    recipient_list = [user.email]
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False
        )
        logger.info(f"Dispatched provider invitation email to {user.email} for facility {facility_name}")
        return True
    except Exception as exc:
        # Development environment or SMTP unconfigured: safely log without exposing the token
        logger.warning(
            f"Email dispatch to {user.email} failed: {exc.__class__.__name__}. "
            "Ensure EMAIL_BACKEND or SMTP credentials are configured."
        )
        return False
