"""Serializers for facility-scoped administrative management."""
from rest_framework import serializers
from apps.facilities.models import Hospital, Clinic, FacilityDepartment, FacilityStatus

class FacilitySettingsSerializer(serializers.Serializer):
    """
    Facility settings update serializer strictly scoped to permitted operational fields.
    
    Security & Isolation Rules:
    - Facility administrators can only modify their own facility.
    - Ownership transfer (admin_user) is strictly prevented.
    - Activation status is strictly read-only for facility admins (managed by platform admin).
    - Facility type and IDs cannot be changed.
    """
    id = serializers.UUIDField(read_only=True)
    type = serializers.SerializerMethodField(read_only=True)
    name = serializers.CharField(max_length=255, required=False)
    name_ar = serializers.CharField(max_length=255, required=False, allow_blank=True)
    photo = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(max_length=128, required=False)
    address = serializers.CharField(required=False)
    address_ar = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False)
    operating_hours = serializers.CharField(max_length=128, required=False)
    operating_hours_ar = serializers.CharField(max_length=128, required=False, allow_blank=True)
    about = serializers.CharField(required=False)
    about_ar = serializers.CharField(required=False, allow_blank=True)
    google_maps_url = serializers.URLField(required=False, allow_blank=True)
    emergency_available = serializers.BooleanField(required=False)
    insurance_plans = serializers.CharField(required=False, allow_blank=True)
    primary_specialty = serializers.CharField(max_length=128, required=False)
    default_available_days = serializers.JSONField(required=False)
    default_standard_slots = serializers.JSONField(required=False)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_type(self, obj):
        return 'hospital' if isinstance(obj, Hospital) else 'clinic'

    def to_representation(self, instance):
        data = {
            'id': str(instance.id),
            'type': self.get_type(instance),
            'name': instance.name,
            'name_ar': instance.name_ar,
            'photo': instance.photo,
            'location': instance.location,
            'address': instance.address,
            'address_ar': instance.address_ar,
            'phone': instance.phone,
            'operating_hours': instance.operating_hours,
            'operating_hours_ar': instance.operating_hours_ar,
            'about': instance.about,
            'about_ar': instance.about_ar,
            'google_maps_url': getattr(instance, 'google_maps_url', '') or '',
            'default_available_days': getattr(instance, 'default_available_days', []) or [],
            'default_standard_slots': getattr(instance, 'default_standard_slots', []) or [],
            'defaultAvailableDays': getattr(instance, 'default_available_days', []) or [],
            'defaultStandardSlots': getattr(instance, 'default_standard_slots', []) or [],
            'status': instance.status,
            'created_at': instance.created_at,
            'updated_at': instance.updated_at,
        }
        if isinstance(instance, Hospital):
            data['emergency_available'] = instance.emergency_available
            data['insurance_plans'] = instance.insurance_plans
        elif isinstance(instance, Clinic):
            data['primary_specialty'] = instance.primary_specialty
            data['insurance_plans'] = instance.insurance_plans
        return data

    def update(self, instance, validated_data):
        # Permitted fields only
        permitted_fields = [
            'name', 'name_ar', 'photo', 'location', 'address', 'address_ar',
            'phone', 'operating_hours', 'operating_hours_ar', 'about', 'about_ar',
            'google_maps_url', 'insurance_plans', 'emergency_available', 'primary_specialty',
            'default_available_days', 'default_standard_slots',
        ]
        if isinstance(instance, Hospital):
            permitted_fields.append('emergency_available')
            permitted_fields.append('insurance_plans')
        elif isinstance(instance, Clinic):
            permitted_fields.append('primary_specialty')
            permitted_fields.append('insurance_plans')

        for field in permitted_fields:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        instance.save()
        return instance

class FacilityDepartmentManageSerializer(serializers.ModelSerializer):
    """Clinical department serializer within a hospital."""
    doctor_count = serializers.SerializerMethodField()

    class Meta:
        model = FacilityDepartment
        fields = ['id', 'name', 'head_of_department', 'bed_capacity', 'doctor_count', 'created_at']
        read_only_fields = ['id', 'doctor_count', 'created_at']

    def get_doctor_count(self, obj):
        from apps.doctors.models import Doctor
        if not obj.hospital_id:
            return 0
        return Doctor.objects.filter(hospital_id=obj.hospital_id, specialty__iexact=obj.name).count()

class AdminFacilityStatusUpdateSerializer(serializers.Serializer):
    """Platform administrator facility activation/deactivation payload."""
    status = serializers.ChoiceField(
        choices=FacilityStatus.choices,
        required=True
    )

class AdminProviderCreateSerializer(serializers.Serializer):
    """Platform administrator creation payload for new Hospitals and Clinics."""
    type = serializers.ChoiceField(choices=['hospital', 'clinic'], default='hospital')
    name = serializers.CharField(max_length=255)
    name_ar = serializers.CharField(max_length=255, required=False, allow_blank=True)
    photo = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(max_length=128, default='Dubai')
    address = serializers.CharField(required=False, allow_blank=True)
    address_ar = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    operating_hours = serializers.CharField(max_length=128, default='Open 24/7')
    operating_hours_ar = serializers.CharField(max_length=128, required=False, allow_blank=True)
    about = serializers.CharField(required=False, allow_blank=True)
    about_ar = serializers.CharField(required=False, allow_blank=True)
    google_maps_url = serializers.URLField(required=False, allow_blank=True)
    emergency_available = serializers.BooleanField(default=True)
    insurance_plans = serializers.CharField(required=False, allow_blank=True)
    primary_specialty = serializers.CharField(max_length=128, required=False, allow_blank=True)
    country = serializers.CharField(max_length=128, required=False, default='UAE')
    emirate = serializers.CharField(max_length=128, required=False, allow_blank=True)
    area = serializers.CharField(max_length=128, required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=11, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=11, decimal_places=7, required=False, allow_null=True)
    phone_dial_code = serializers.CharField(max_length=16, required=False, default='+971')
    website = serializers.CharField(max_length=500, required=False, allow_blank=True)
    logo = serializers.CharField(required=False, allow_blank=True)
    facility_category = serializers.CharField(max_length=32, required=False, default='Hospital')
    manager_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    manager_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    manager_email = serializers.EmailField(required=False, allow_blank=True)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(max_length=128, required=False, allow_blank=True)
