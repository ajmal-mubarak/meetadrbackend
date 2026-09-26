"""Custom SimpleJWT Token Classes and Session Ceiling Enforcement."""
import time
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from apps.accounts.models import User

class MeetAdrAccessToken(AccessToken):
    """Access token carrying user profile and facility context claims."""
    pass

class MeetAdrRefreshToken(RefreshToken):
    """Refresh token enforcing token family protection and absolute session ceiling."""
    access_token_class = MeetAdrAccessToken

    @classmethod
    def for_user(cls, user: User, session_start_iat: int = None):
        """Generate token pair with custom claims and session ceiling timestamp."""
        token = super().for_user(user)

        # Set or preserve session_start_iat
        current_time = int(time.time())
        token['session_start_iat'] = session_start_iat if session_start_iat is not None else current_time

        # Custom claims on token (SimpleJWT copies all custom payload claims to access_token)
        token['user_id'] = str(user.id)
        token['email'] = user.email
        token['role'] = user.role
        token['name'] = user.name

        # Resolve doctor or facility context
        doctor_id = None
        facility_id = None
        facility_type = None

        if hasattr(user, 'doctor_profile'):
            doc = user.doctor_profile
            doctor_id = str(doc.id)
            if doc.hospital_id:
                facility_id = str(doc.hospital_id)
                facility_type = 'hospital'
            elif doc.clinic_id:
                facility_id = str(doc.clinic_id)
                facility_type = 'clinic'
        elif hasattr(user, 'facility_admin'):
            admin_prof = user.facility_admin
            if admin_prof.hospital_id:
                facility_id = str(admin_prof.hospital_id)
                facility_type = 'hospital'
            elif admin_prof.clinic_id:
                facility_id = str(admin_prof.clinic_id)
                facility_type = 'clinic'

        token['doctor_id'] = doctor_id
        token['facility_id'] = facility_id
        token['facility_type'] = facility_type

        return token

    def check_session_ceiling(self):
        """
        Verify that the session has not exceeded the absolute maximum lifetime (default 30 days).
        Prevents indefinite sliding refresh token attacks.
        """
        session_start = self.payload.get('session_start_iat')
        if session_start is None:
            # Fallback to iat if claim not present
            session_start = self.payload.get('iat', int(time.time()))

        max_lifetime_days = getattr(settings, 'AUTH_SESSION_MAX_DAYS', 30)
        max_lifetime_seconds = max_lifetime_days * 86400

        current_time = int(time.time())
        if current_time - session_start > max_lifetime_seconds:
            raise AuthenticationFailed(
                detail={
                    'code': 'SESSION_EXPIRED',
                    'detail': f'Session reached absolute maximum {max_lifetime_days}-day limit. Please sign in again.'
                }
            )
