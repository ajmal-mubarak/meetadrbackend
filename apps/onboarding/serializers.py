"""Serializers for provider onboarding applications and administrative reviews."""
from rest_framework import serializers
from apps.onboarding.models import ProviderRequest, ProviderType, RequestStatus

class ProviderRequestPublicCreateSerializer(serializers.ModelSerializer):
    """
    Public submission serializer for hospital and clinic partnership requests.
    
    Security & Domain Invariants:
    - Only 'hospital' and 'clinic' provider types are permitted.
    - Individual doctor registration through this flow is strictly rejected.
    - Status is strictly enforced to 'pending' by the server.
    - All administrative review fields are read-only.
    """
    provider_type = serializers.ChoiceField(
        choices=ProviderType.choices,
        error_messages={
            'invalid_choice': "Invalid provider type. Only 'hospital' and 'clinic' are accepted."
        }
    )
    name = serializers.CharField(max_length=255, min_length=2)
    name_ar = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    contact_person = serializers.CharField(max_length=255, min_length=2)
    contact_number = serializers.CharField(max_length=32, min_length=6)
    email = serializers.EmailField()
    country = serializers.CharField(max_length=64, default='United Arab Emirates')
    location = serializers.CharField(max_length=128, min_length=2)
    address = serializers.CharField(required=False, allow_blank=True, default='')
    admin_notes = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = ProviderRequest
        fields = [
            'id',
            'provider_type',
            'name',
            'name_ar',
            'contact_person',
            'contact_number',
            'email',
            'country',
            'location',
            'address',
            'status',
            'admin_notes',
            'submitted_at',
        ]
        read_only_fields = ['id', 'status', 'submitted_at']

    def validate_provider_type(self, value):
        val = str(value).lower().strip()
        if val == 'doctor':
            raise serializers.ValidationError(
                "Individual doctors must not register independently. "
                "Provider onboarding is strictly for Hospitals and Clinics."
            )
        if val not in [ProviderType.HOSPITAL, ProviderType.CLINIC]:
            raise serializers.ValidationError(
                "Invalid provider type. Only 'hospital' and 'clinic' are permitted."
            )
        return val

    def validate_email(self, value):
        return value.lower().strip()

    def create(self, validated_data):
        # Force status to PENDING regardless of client payload
        validated_data['status'] = RequestStatus.PENDING
        validated_data.pop('reviewed_by', None)
        validated_data.pop('reviewed_at', None)
        validated_data.pop('hospital', None)
        validated_data.pop('clinic', None)
        return super().create(validated_data)

class AdminProviderRequestListSerializer(serializers.ModelSerializer):
    """Platform administrator view of provider onboarding applications."""
    reviewed_by_email = serializers.SerializerMethodField()
    facility_id = serializers.SerializerMethodField()
    facility_name = serializers.SerializerMethodField()

    class Meta:
        model = ProviderRequest
        fields = [
            'id',
            'provider_type',
            'name',
            'name_ar',
            'contact_person',
            'contact_number',
            'email',
            'country',
            'location',
            'address',
            'status',
            'admin_notes',
            'reviewed_by',
            'reviewed_by_email',
            'reviewed_at',
            'submitted_at',
            'facility_id',
            'facility_name',
        ]
        read_only_fields = fields

    def get_reviewed_by_email(self, obj):
        return obj.reviewed_by.email if obj.reviewed_by else None

    def get_facility_id(self, obj):
        if obj.hospital_id:
            return str(obj.hospital_id)
        if obj.clinic_id:
            return str(obj.clinic_id)
        return None

    def get_facility_name(self, obj):
        if obj.hospital:
            return obj.hospital.name
        if obj.clinic:
            return obj.clinic.name
        return None

class AdminProviderRequestStatusUpdateSerializer(serializers.Serializer):
    """Platform administrator approval/rejection state transition payload."""
    status = serializers.ChoiceField(
        choices=['approved', 'rejected'],
        required=True,
        error_messages={
            'invalid_choice': "Status must transition to either 'approved' or 'rejected'."
        }
    )
    admin_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )

class ProviderRequestPublicStatusSerializer(serializers.ModelSerializer):
    """
    Public, privacy-preserving serializer for querying application status by reference ID.
    
    Privacy Invariants:
    - Exposes strictly non-sensitive status and timestamp information.
    - Sensitive fields (applicant email, phone, contact person, address, license, 
      admin notes, review actor, and internal facility details) are strictly excluded.
    """
    class Meta:
        model = ProviderRequest
        fields = [
            'id',
            'provider_type',
            'status',
            'submitted_at',
        ]
        read_only_fields = fields
