"""Accounts, Authentication and Patient Profile Serializers."""
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from apps.accounts.models import User, UserRole, PatientProfile, PatientDependent, BloodGroup, RelationType
from apps.accounts.tokens import MeetAdrRefreshToken

class UserSummarySerializer(serializers.ModelSerializer):
    """Safe, minimal summary of authenticated user profile."""
    doctor_id = serializers.SerializerMethodField()
    facility_id = serializers.SerializerMethodField()
    facility_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'phone', 'role', 'avatar',
            'doctor_id', 'facility_id', 'facility_type', 'date_joined'
        ]
        read_only_fields = ['id', 'email', 'role', 'date_joined']

    def get_doctor_id(self, obj):
        if hasattr(obj, 'doctor_profile'):
            return str(obj.doctor_profile.id)
        return None

    def get_facility_id(self, obj):
        if hasattr(obj, 'doctor_profile'):
            doc = obj.doctor_profile
            return str(doc.hospital_id or doc.clinic_id or '') or None
        elif hasattr(obj, 'facility_admin'):
            admin_prof = obj.facility_admin
            return str(admin_prof.hospital_id or admin_prof.clinic_id or '') or None
        return None

    def get_facility_type(self, obj):
        if hasattr(obj, 'doctor_profile'):
            doc = obj.doctor_profile
            return 'hospital' if doc.hospital_id else ('clinic' if doc.clinic_id else None)
        elif hasattr(obj, 'facility_admin'):
            admin_prof = obj.facility_admin
            return 'hospital' if admin_prof.hospital_id else ('clinic' if admin_prof.clinic_id else None)
        return None

class PatientDependentSerializer(serializers.ModelSerializer):
    """Serializer for patient dependent profiles."""
    class Meta:
        model = PatientDependent
        fields = [
            'id', 'name', 'relation', 'gender', 'dob', 'blood_group',
            'allergies', 'medical_notes', 'emergency_contact',
            'insurance_provider', 'insurance_number', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class PatientProfileSerializer(serializers.ModelSerializer):
    """Detailed patient medical and demographic profile with dependents."""
    dependents = PatientDependentSerializer(many=True, read_only=True)

    class Meta:
        model = PatientProfile
        fields = [
            'id', 'gender', 'dob', 'blood_group', 'emergency_contact',
            'allergies', 'insurance_provider', 'insurance_number',
            'dependents', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class CurrentUserSerializer(serializers.ModelSerializer):
    """Full authenticated profile for /api/v1/auth/me/ endpoint."""
    patient_profile = PatientProfileSerializer(read_only=True)
    doctor_id = serializers.SerializerMethodField()
    facility_id = serializers.SerializerMethodField()
    facility_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'name', 'phone', 'role', 'avatar',
            'doctor_id', 'facility_id', 'facility_type',
            'patient_profile', 'date_joined'
        ]
        read_only_fields = ['id', 'email', 'role', 'date_joined']

    def get_doctor_id(self, obj):
        return str(obj.doctor_profile.id) if hasattr(obj, 'doctor_profile') else None

    def get_facility_id(self, obj):
        if hasattr(obj, 'doctor_profile'):
            doc = obj.doctor_profile
            return str(doc.hospital_id or doc.clinic_id or '') or None
        elif hasattr(obj, 'facility_admin'):
            admin_prof = obj.facility_admin
            return str(admin_prof.hospital_id or admin_prof.clinic_id or '') or None
        return None

    def get_facility_type(self, obj):
        if hasattr(obj, 'doctor_profile'):
            doc = obj.doctor_profile
            return 'hospital' if doc.hospital_id else ('clinic' if doc.clinic_id else None)
        elif hasattr(obj, 'facility_admin'):
            admin_prof = obj.facility_admin
            return 'hospital' if admin_prof.hospital_id else ('clinic' if admin_prof.clinic_id else None)
        return None

class PatientRegisterSerializer(serializers.Serializer):
    """
    Public patient registration serializer.
    Strictly hardcodes role='patient', is_staff=False, is_superuser=False.
    Any submitted privileged keys are discarded.
    """
    name = serializers.CharField(max_length=255, required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')

    def validate_email(self, value):
        normalized_email = value.lower().strip()
        if User.objects.filter(email=normalized_email).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return normalized_email

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            name=validated_data['name'],
            password=validated_data['password'],
            phone=validated_data.get('phone', ''),
            role=UserRole.PATIENT,
            is_staff=False,
            is_superuser=False
        )
        # Ensure a clean PatientProfile is created for every new patient
        PatientProfile.objects.create(user=user)
        return user

class LoginSerializer(serializers.Serializer):
    """Credentials authentication serializer."""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    def validate(self, attrs):
        email = attrs.get('email', '').lower().strip()
        password = attrs.get('password', '')

        if not email or not password:
            raise AuthenticationFailed("Must include both email and password.")

        user = authenticate(email=email, password=password)
        if not user:
            raise AuthenticationFailed("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationFailed("This account has been deactivated.")

        attrs['user'] = user
        return attrs

class CustomTokenRefreshSerializer(serializers.Serializer):
    """Token refresh serializer enforcing rotation and 30-day session lifetime ceiling."""
    refresh = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        refresh_token_str = attrs.get('refresh')
        
        # If not provided in body, fallback will be handled by the view via cookie
        if not refresh_token_str:
            request = self.context.get('request')
            if request:
                from django.conf import settings
                cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'meetadr_refresh_token')
                refresh_token_str = request.COOKIES.get(cookie_name)

        if not refresh_token_str:
            raise AuthenticationFailed("No refresh token provided in body or cookie.")

        try:
            old_refresh = MeetAdrRefreshToken(refresh_token_str)
        except Exception as e:
            raise AuthenticationFailed("Invalid or expired refresh token.")

        # Enforce 30-day absolute ceiling
        old_refresh.check_session_ceiling()

        session_start_iat = old_refresh.payload.get('session_start_iat')
        user_id = old_refresh.payload.get('user_id')

        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            raise AuthenticationFailed("User not found or deactivated.")

        # Rotate token
        new_refresh = MeetAdrRefreshToken.for_user(user, session_start_iat=session_start_iat)

        # Blacklist old token
        try:
            old_refresh.blacklist()
        except AttributeError:
            pass

        return {
            'access': str(new_refresh.access_token),
            'refresh': str(new_refresh)
        }
