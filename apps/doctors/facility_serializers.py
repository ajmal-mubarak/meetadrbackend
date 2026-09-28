"""Serializers for facility-scoped doctor onboarding and management."""
from rest_framework import serializers
from apps.doctors.models import Doctor, DoctorSchedule
from apps.facilities.models import Hospital, Clinic, FacilityStatus

DEFAULT_AVAILABLE_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday']
DEFAULT_STANDARD_SLOTS = [
    '09:00 - 09:30', '09:30 - 10:00', '10:00 - 10:30',
    '11:00 - 11:30', '14:00 - 14:30', '15:00 - 15:30'
]

class FacilityDoctorSerializer(serializers.ModelSerializer):
    """
    Facility-scoped doctor management serializer.
    
    Security & Domain Invariants:
    1. Facility assignment is strictly derived from the authenticated administrator.
    2. Client-supplied hospitalId, clinicId, or facilityId are strictly rejected/ignored.
    3. Reassignment across facilities is strictly forbidden.
    4. XOR invariant (Hospital XOR Clinic) is enforced server-side.
    5. Ratings, review counts, and status cannot be mass-assigned.
    """
    available_days = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=DEFAULT_AVAILABLE_DAYS
    )
    standard_slots = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=DEFAULT_STANDARD_SLOTS
    )
    slot_duration_minutes = serializers.IntegerField(
        required=False,
        default=30
    )
    location = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True
    )
    facility_id = serializers.SerializerMethodField()
    facility_name = serializers.SerializerMethodField()
    facility_type = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            'id',
            'name',
            'name_ar',
            'photo',
            'specialty',
            'special_interests',
            'experience_years',
            'experience_text',
            'experience_text_ar',
            'education',
            'consultation_fee',
            'location',
            'about',
            'about_ar',
            'rating',
            'review_count',
            'status',
            'facility_id',
            'facility_name',
            'facility_type',
            'available_days',
            'standard_slots',
            'slot_duration_minutes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'rating',
            'review_count',
            'status',
            'facility_id',
            'facility_name',
            'facility_type',
            'created_at',
            'updated_at',
        ]

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

    def get_facility_type(self, obj):
        if obj.hospital_id:
            return 'hospital'
        if obj.clinic_id:
            return 'clinic'
        return None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        schedule = getattr(instance, 'schedule', None)
        if schedule:
            ret['available_days'] = schedule.available_days
            ret['standard_slots'] = schedule.standard_slots
            ret['slot_duration_minutes'] = schedule.slot_duration_minutes
        return ret

    def create(self, validated_data):
        facility_type = self.context.get('facility_type')
        facility = self.context.get('facility')

        if not facility or not facility_type:
            raise serializers.ValidationError("Authorized facility context is required.")

        # Extract schedule data
        available_days = validated_data.pop('available_days', DEFAULT_AVAILABLE_DAYS)
        standard_slots = validated_data.pop('standard_slots', DEFAULT_STANDARD_SLOTS)
        slot_duration = validated_data.pop('slot_duration_minutes', 30)

        # Disallow mass assignment of internal fields
        for forbidden in ['hospital', 'clinic', 'hospital_id', 'clinic_id', 'rating', 'review_count', 'status', 'user']:
            validated_data.pop(forbidden, None)

        # Enforce server-side facility binding strictly
        if facility_type == 'hospital':
            validated_data['hospital'] = facility
            validated_data['clinic'] = None
        elif facility_type == 'clinic':
            validated_data['clinic'] = facility
            validated_data['hospital'] = None

        if not validated_data.get('location'):
            validated_data['location'] = getattr(facility, 'location', 'United Arab Emirates')

        validated_data['status'] = FacilityStatus.ACTIVE

        doctor = Doctor.objects.create(**validated_data)

        # Create schedule
        DoctorSchedule.objects.create(
            doctor=doctor,
            available_days=available_days,
            standard_slots=standard_slots,
            slot_duration_minutes=slot_duration
        )

        return doctor

    def update(self, instance, validated_data):
        # Strict Reassignment Protection: ignore or disallow any facility changes
        for forbidden in ['hospital', 'clinic', 'hospital_id', 'clinic_id', 'rating', 'review_count', 'status', 'user']:
            validated_data.pop(forbidden, None)

        # Schedule updates
        schedule = getattr(instance, 'schedule', None)
        if schedule:
            schedule_updated = False
            if 'available_days' in validated_data:
                schedule.available_days = validated_data.pop('available_days')
                schedule_updated = True
            if 'standard_slots' in validated_data:
                schedule.standard_slots = validated_data.pop('standard_slots')
                schedule_updated = True
            if 'slot_duration_minutes' in validated_data:
                schedule.slot_duration_minutes = validated_data.pop('slot_duration_minutes')
                schedule_updated = True
            if schedule_updated:
                schedule.save()
        else:
            validated_data.pop('available_days', None)
            validated_data.pop('standard_slots', None)
            validated_data.pop('slot_duration_minutes', None)

        return super().update(instance, validated_data)

class FacilityDoctorStatusSerializer(serializers.Serializer):
    """Payload to toggle or update a doctor's Active / Deactivated status."""
    status = serializers.ChoiceField(
        choices=FacilityStatus.choices,
        required=True
    )
