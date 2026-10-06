"""Accounts, Authentication and Patient Profile API Views."""
from django.conf import settings
from rest_framework import views, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from apps.accounts.models import User, UserRole, PatientProfile, PatientDependent
from apps.accounts.permissions import (
    IsPatient,
    IsDoctor,
    HasClinicalRelationshipWithPatient
)
from apps.accounts.serializers import (
    UserSummarySerializer,
    CurrentUserSerializer,
    PatientProfileSerializer,
    PatientDependentSerializer,
    PatientRegisterSerializer,
    LoginSerializer,
    CustomTokenRefreshSerializer
)
import hashlib
from django.db import transaction
from apps.accounts.tokens import MeetAdrRefreshToken
from apps.audit.utils import log_audit_event
from apps.notifications.services import notify_facility_setup_completed
from apps.onboarding.models import ProviderInvitationToken
from apps.facilities.models import FacilityStatus
from apps.accounts.serializers import (
    ProviderSetupValidateSerializer,
    ProviderSetupCompleteSerializer
)

def set_auth_refresh_cookie(response, refresh_token_str: str):
    """Set the HttpOnly secure refresh token cookie on HTTP response."""
    cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'meetadr_refresh_token')
    cookie_path = getattr(settings, 'AUTH_COOKIE_PATH', '/api/v1/auth/')
    httponly = getattr(settings, 'AUTH_COOKIE_HTTPONLY', True)
    secure = getattr(settings, 'AUTH_COOKIE_SECURE', False)
    samesite = getattr(settings, 'AUTH_COOKIE_SAMESITE', 'Lax')
    
    # 7 days max age
    max_age = 7 * 24 * 60 * 60

    response.set_cookie(
        key=cookie_name,
        value=refresh_token_str,
        max_age=max_age,
        path=cookie_path,
        httponly=httponly,
        secure=secure,
        samesite=samesite
    )

def clear_auth_refresh_cookie(response):
    """Clear the refresh token cookie."""
    cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'meetadr_refresh_token')
    cookie_path = getattr(settings, 'AUTH_COOKIE_PATH', '/api/v1/auth/')
    samesite = getattr(settings, 'AUTH_COOKIE_SAMESITE', 'Lax')
    response.delete_cookie(cookie_name, path=cookie_path, samesite=samesite)

from drf_spectacular.utils import extend_schema

class LoginView(views.APIView):
    """Authenticates credentials, generates JWT tokens and sets HttpOnly cookie."""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses={200: UserSummarySerializer},
        description="Authenticates credentials, generates JWT tokens and sets HttpOnly cookie."
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        refresh = MeetAdrRefreshToken.for_user(user)

        log_audit_event(
            action='USER_LOGIN_SUCCESS',
            target_model='User',
            target_id=str(user.id),
            actor=user,
            request=request,
            change_summary={'role': user.role, 'email': user.email}
        )

        response_data = {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSummarySerializer(user).data
        }
        response = Response(response_data, status=status.HTTP_200_OK)
        set_auth_refresh_cookie(response, str(refresh))
        return response

class RegisterView(views.APIView):
    """Public patient registration endpoint."""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    serializer_class = PatientRegisterSerializer

    @extend_schema(
        request=PatientRegisterSerializer,
        responses={201: UserSummarySerializer},
        description="Public patient registration endpoint."
    )
    def post(self, request):
        serializer = PatientRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = MeetAdrRefreshToken.for_user(user)

        log_audit_event(
            action='PATIENT_REGISTRATION',
            target_model='User',
            target_id=str(user.id),
            actor=user,
            request=request,
            change_summary={'email': user.email, 'role': user.role}
        )

        response_data = {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSummarySerializer(user).data
        }
        response = Response(response_data, status=status.HTTP_201_CREATED)
        set_auth_refresh_cookie(response, str(refresh))
        return response

class RefreshTokenView(views.APIView):
    """Exchanges valid refresh token for rotated refresh token and new access token."""
    permission_classes = [AllowAny]
    serializer_class = CustomTokenRefreshSerializer

    @extend_schema(
        request=CustomTokenRefreshSerializer,
        description="Exchanges valid refresh token for rotated refresh token and new access token."
    )
    def post(self, request):
        serializer = CustomTokenRefreshSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        tokens = serializer.validated_data

        response = Response({'access': tokens['access'], 'refresh': tokens['refresh']}, status=status.HTTP_200_OK)
        set_auth_refresh_cookie(response, tokens['refresh'])
        return response

class LogoutView(views.APIView):
    """Revokes refresh token, adds jti to blacklist, and clears HttpOnly cookie."""
    permission_classes = [AllowAny]

    def post(self, request):
        cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'meetadr_refresh_token')
        refresh_str = request.data.get('refresh') or request.COOKIES.get(cookie_name)

        if refresh_str:
            try:
                token = MeetAdrRefreshToken(refresh_str)
                token.blacklist()
            except Exception:
                pass  # Already blacklisted, expired, or invalid

        if request.user and request.user.is_authenticated:
            log_audit_event(
                action='USER_LOGOUT',
                target_model='User',
                target_id=str(request.user.id),
                actor=request.user,
                request=request
            )

        response = Response({'detail': 'Successfully logged out.'}, status=status.HTTP_200_OK)
        clear_auth_refresh_cookie(response)
        return response

class CurrentUserView(views.APIView):
    """Retrieves or updates authenticated user profile (/api/v1/auth/me/)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        user = request.user
        allowed_fields = ['name', 'phone', 'avatar']
        for field in allowed_fields:
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save()

        # If patient has patient_profile and updates clinical fields
        if hasattr(user, 'patient_profile') and any(k in request.data for k in ['gender', 'dob', 'blood_group', 'emergency_contact', 'allergies', 'insurance_provider', 'insurance_number']):
            profile = user.patient_profile
            for k in ['gender', 'dob', 'blood_group', 'emergency_contact', 'allergies', 'insurance_provider', 'insurance_number']:
                if k in request.data:
                    setattr(profile, k, request.data[k])
            profile.save()

        serializer = CurrentUserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

class PatientProfileView(views.APIView):
    """Direct access to authenticated patient's clinical profile."""
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request):
        profile, _ = PatientProfile.objects.get_or_create(user=request.user)
        serializer = PatientProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        profile, _ = PatientProfile.objects.get_or_create(user=request.user)
        serializer = PatientProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        return self.put(request)

class PatientDependentViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for managing dependents belonging strictly to the authenticated patient.
    Enforces strict IDOR protection by scoping querysets exclusively to request.user.patient_profile.
    """
    serializer_class = PatientDependentSerializer
    permission_classes = [IsAuthenticated, IsPatient]

    def get_queryset(self):
        if not hasattr(self.request.user, 'patient_profile'):
            return PatientDependent.objects.none()
        return PatientDependent.objects.filter(profile=self.request.user.patient_profile)

    def perform_create(self, serializer):
        profile, _ = PatientProfile.objects.get_or_create(user=self.request.user)
        instance = serializer.save(profile=profile)
        log_audit_event(
            action='DEPENDENT_CREATED',
            target_model='PatientDependent',
            target_id=str(instance.id),
            actor=self.request.user,
            request=self.request,
            change_summary={'name': instance.name, 'relation': instance.relation}
        )

    def perform_destroy(self, instance):
        log_audit_event(
            action='DEPENDENT_DELETED',
            target_model='PatientDependent',
            target_id=str(instance.id),
            actor=self.request.user,
            request=self.request,
            change_summary={'name': instance.name}
        )
        instance.delete()

class DoctorPatientMedicalProfileView(views.APIView):
    """
    Allows a doctor to access a patient's medical profile IF AND ONLY IF an active clinical
    encounter (Appointment confirmed or completed) exists between them.
    Blocks arbitrary browsing of global patient records (404/403).
    """
    permission_classes = [IsAuthenticated, IsDoctor]

    def get(self, request, patient_id):
        # First check if target is a PatientProfile
        profile = PatientProfile.objects.filter(id=patient_id).first()
        target_obj = profile

        if not target_obj:
            # Check if target is a PatientDependent
            dependent = PatientDependent.objects.filter(id=patient_id).first()
            target_obj = dependent

        if not target_obj:
            raise NotFound("Patient clinical profile not found.")

        # Check clinical relationship permission
        perm = HasClinicalRelationshipWithPatient()
        if not perm.has_object_permission(request, self, target_obj):
            raise NotFound("Patient clinical profile not found or no authorized clinical relationship.")

        if isinstance(target_obj, PatientProfile):
            serializer = PatientProfileSerializer(target_obj)
        else:
            serializer = PatientDependentSerializer(target_obj)

        log_audit_event(
            action='DOCTOR_VIEWED_PATIENT_CHART',
            target_model=target_obj.__class__.__name__,
            target_id=str(target_obj.id),
            actor=request.user,
            request=request
        )

        return Response(serializer.data, status=status.HTTP_200_OK)

class ProviderSetupValidateView(views.APIView):
    """
    Public validation endpoint for single-use provider administrator invitation tokens.
    POST /api/v1/auth/provider-setup/validate/
    """
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = ProviderSetupValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_token = serializer.validated_data['token']

        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        invitation = ProviderInvitationToken.objects.filter(token_hash=token_hash).select_related(
            'user', 'user__hospital_facility', 'user__clinic_facility'
        ).first()

        # Generic failure behavior to prevent token/state enumeration oracle
        if not invitation or invitation.is_used or invitation.is_expired:
            return Response({
                "valid": False,
                "error": "InvalidInvitation",
                "message": "Invalid, expired, or previously consumed setup invitation token."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = invitation.user
        facility = getattr(user, 'hospital_facility', None) or getattr(user, 'clinic_facility', None)
        facility_name = facility.name if facility else 'Healthcare Facility'
        facility_type = 'hospital' if hasattr(user, 'hospital_facility') and user.hospital_facility else 'clinic'

        return Response({
            "valid": True,
            "email": user.email,
            "facility_name": facility_name,
            "facility_type": facility_type
        }, status=status.HTTP_200_OK)

class ProviderSetupCompleteView(views.APIView):
    """
    Public password establishment endpoint for newly approved facility administrators.
    POST /api/v1/auth/provider-setup/complete/
    """
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = ProviderSetupCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_token = serializer.validated_data['token']
        password = serializer.validated_data['password']

        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        invitation = ProviderInvitationToken.objects.filter(token_hash=token_hash).select_related('user').first()

        # Generic failure behavior to prevent token/state enumeration oracle
        if not invitation or invitation.is_used or invitation.is_expired:
            return Response({
                "error": "InvalidInvitation",
                "message": "Invalid, expired, or previously consumed setup invitation token."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = invitation.user
            user.set_password(password)
            user.role = UserRole.HOSPITAL  # Strict server-side enforcement
            user.is_active = True
            user.save()

            invitation.is_used = True
            invitation.save()

            facility = getattr(user, 'hospital_facility', None) or getattr(user, 'clinic_facility', None)
            if facility:
                facility.status = FacilityStatus.ACTIVE
                facility.save(update_fields=['status', 'updated_at'])
                notify_facility_setup_completed(user, facility)

            log_audit_event(
                action="INVITATION_ACCEPTED",
                target_model="User",
                target_id=str(user.id),
                actor=user,
                change_summary={
                    "email": user.email,
                    "role": user.role,
                },
                request=request
            )

        refresh = MeetAdrRefreshToken.for_user(user)

        response = Response({
            "success": True,
            "message": "Account setup successfully completed.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSummarySerializer(user).data
        }, status=status.HTTP_200_OK)
        set_auth_refresh_cookie(response, str(refresh))
        return response
