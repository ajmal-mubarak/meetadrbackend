"""Doctor Directory and Availability Serializers."""
from rest_framework import serializers
from apps.doctors.models import Doctor, DoctorSchedule
from apps.facilities.serializers import HospitalListSerializer, ClinicListSerializer

VALID_WEEKDAYS = {
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
}

class DoctorScheduleSerializer(serializers.ModelSerializer):
    """Doctor availability schedule and standard slot duration."""
    availableDays = serializers.JSONField(source='available_days', read_only=True)
    standardSlots = serializers.JSONField(source='standard_slots', read_only=True)
    slotDurationMinutes = serializers.IntegerField(source='slot_duration_minutes', read_only=True)

    class Meta:
        model = DoctorSchedule
        fields = [
            'available_days',
            'availableDays',
            'standard_slots',
            'standardSlots',
            'slot_duration_minutes',
            'slotDurationMinutes',
        ]


class DoctorScheduleUpdateSerializer(serializers.Serializer):
    """Serializer for updating doctor practicing schedule and standard slots."""
    available_days = serializers.ListField(
        child=serializers.CharField(max_length=16),
        required=False
    )
    availableDays = serializers.ListField(
        child=serializers.CharField(max_length=16),
        required=False
    )
    standard_slots = serializers.ListField(
        child=serializers.CharField(max_length=32),
        required=False
    )
    standardSlots = serializers.ListField(
        child=serializers.CharField(max_length=32),
        required=False
    )
    slot_duration_minutes = serializers.IntegerField(
        min_value=10,
        max_value=120,
        required=False
    )
    slotDurationMinutes = serializers.IntegerField(
        min_value=10,
        max_value=120,
        required=False
    )

    def validate(self, attrs):
        # Normalize camelCase aliases into canonical snake_case
        if 'availableDays' in attrs and 'available_days' not in attrs:
            attrs['available_days'] = attrs.pop('availableDays')
        if 'standardSlots' in attrs and 'standard_slots' not in attrs:
            attrs['standard_slots'] = attrs.pop('standardSlots')
        if 'slotDurationMinutes' in attrs and 'slot_duration_minutes' not in attrs:
            attrs['slot_duration_minutes'] = attrs.pop('slotDurationMinutes')

        days = attrs.get('available_days')
        if days is not None:
            if not isinstance(days, list):
                raise serializers.ValidationError({'available_days': "Must be a list of weekdays."})
            if len(days) > 7:
                raise serializers.ValidationError({'available_days': "Cannot specify more than 7 weekdays."})
            cleaned_days = []
            for d in days:
                if not isinstance(d, str) or d.capitalize() not in VALID_WEEKDAYS:
                    raise serializers.ValidationError({
                        'available_days': f"Invalid weekday '{d}'. Must be one of Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday."
                    })
                day_cap = d.capitalize()
                if day_cap not in cleaned_days:
                    cleaned_days.append(day_cap)
            attrs['available_days'] = cleaned_days

        slots = attrs.get('standard_slots')
        if slots is not None:
            if not isinstance(slots, list):
                raise serializers.ValidationError({'standard_slots': "Must be a list of slot strings."})
            if len(slots) > 50:
                raise serializers.ValidationError({'standard_slots': "Cannot specify more than 50 consultation slots."})
            cleaned_slots = []
            for s in slots:
                if not isinstance(s, str) or not s.strip():
                    raise serializers.ValidationError({
                        'standard_slots': "Slot intervals must be non-empty strings."
                    })
                slot_clean = s.strip()
                if len(slot_clean) > 32:
                    raise serializers.ValidationError({
                        'standard_slots': f"Slot string '{slot_clean}' exceeds maximum allowed length of 32 characters."
                    })
                if slot_clean not in cleaned_slots:
                    cleaned_slots.append(slot_clean)
            attrs['standard_slots'] = cleaned_slots

        return attrs

class DoctorListSerializer(serializers.ModelSerializer):
    """Public list serializer for doctor directory with faceted search fields."""
    hospital_id = serializers.SerializerMethodField()
    hospital_name = serializers.SerializerMethodField()
    hospital_name_ar = serializers.SerializerMethodField()
    clinic_id = serializers.SerializerMethodField()
    clinic_name = serializers.SerializerMethodField()
    available_days = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            'id', 'name', 'name_ar', 'photo', 'specialty',
            'special_interests', 'experience_years', 'experience_text',
            'experience_text_ar', 'rating', 'review_count', 'location',
            'consultation_fee', 'status',
            'hospital_id', 'hospital_name', 'hospital_name_ar',
            'clinic_id', 'clinic_name',
            'about', 'about_ar', 'education', 'available_days'
        ]

    def get_hospital_id(self, obj):
        return str(obj.hospital_id) if obj.hospital_id else None

    def get_hospital_name(self, obj):
        return obj.hospital.name if obj.hospital else None

    def get_hospital_name_ar(self, obj):
        return obj.hospital.name_ar if obj.hospital else None

    def get_clinic_id(self, obj):
        return str(obj.clinic_id) if obj.clinic_id else None

    def get_clinic_name(self, obj):
        return obj.clinic.name if obj.clinic else None

    def get_available_days(self, obj):
        if hasattr(obj, 'schedule'):
            return obj.schedule.available_days
        return []

class DoctorDetailSerializer(DoctorListSerializer):
    """Detailed doctor profile with full facility context and schedule."""
    schedule = DoctorScheduleSerializer(read_only=True)
    facility_details = serializers.SerializerMethodField()

    class Meta(DoctorListSerializer.Meta):
        fields = DoctorListSerializer.Meta.fields + ['schedule', 'facility_details']

    def get_facility_details(self, obj):
        if obj.hospital:
            return {
                'type': 'hospital',
                'id': str(obj.hospital.id),
                'name': obj.hospital.name,
                'name_ar': obj.hospital.name_ar,
                'location': obj.hospital.location,
                'address': obj.hospital.address,
                'phone': obj.hospital.phone,
                'emergency_available': obj.hospital.emergency_available,
            }
        elif obj.clinic:
            return {
                'type': 'clinic',
                'id': str(obj.clinic.id),
                'name': obj.clinic.name,
                'name_ar': obj.clinic.name_ar,
                'location': obj.clinic.location,
                'address': obj.clinic.address,
                'phone': obj.clinic.phone,
                'emergency_available': False,
            }
        return None


class DoctorPublicReviewSerializer(serializers.ModelSerializer):
    """
    Public sanitized review serializer.
    Guarantees strict patient anonymity and zero PII or appointment linkage.
    """
    patientDisplayName = serializers.SerializerMethodField()
    patient_display_name = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        from apps.appointments.models import DoctorReview
        model = DoctorReview
        fields = [
            'id',
            'rating',
            'comment',
            'patientDisplayName',
            'patient_display_name',
            'createdAt',
            'created_at',
        ]
        read_only_fields = fields

    def get_patientDisplayName(self, obj):
        return "Verified Patient"

    def get_patient_display_name(self, obj):
        return "Verified Patient"
