"""Serializers for facility-scoped doctor onboarding and management."""
from rest_framework import serializers
from apps.doctors.models import Doctor, DoctorSchedule
from apps.facilities.models import Hospital, Clinic, FacilityStatus

DEFAULT_AVAILABLE_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
DEFAULT_STANDARD_SLOTS = [
    '08:00 - 08:30', '08:30 - 09:00', '09:00 - 09:30', '09:30 - 10:00',
    '10:00 - 10:30', '10:30 - 11:00', '11:00 - 11:30', '11:30 - 12:00',
    '14:00 - 14:30', '14:30 - 15:00', '15:00 - 15:30', '15:30 - 16:00',
    '16:00 - 16:30', '16:30 - 17:00'
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
    username = serializers.CharField(required=False, write_only=True, allow_blank=True)
    password = serializers.CharField(required=False, write_only=True, allow_blank=True)
    email = serializers.CharField(required=False, write_only=True, allow_blank=True)
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
            'username',
            'password',
            'email',
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
        fac_days = getattr(facility, 'default_available_days', None)
        fac_slots = getattr(facility, 'default_standard_slots', None)
        default_days = list(fac_days) if (fac_days and len(fac_days) > 0) else DEFAULT_AVAILABLE_DAYS
        default_slots = list(fac_slots) if (fac_slots and len(fac_slots) > 0) else DEFAULT_STANDARD_SLOTS

        available_days = validated_data.pop('available_days', None) or default_days
        standard_slots = validated_data.pop('standard_slots', None) or default_slots
        slot_duration = validated_data.pop('slot_duration_minutes', 30)
        username = validated_data.pop('username', None)
        password = validated_data.pop('password', None)
        email = validated_data.pop('email', None)

        # Disallow mass assignment of internal fields
        for forbidden in ['hospital', 'clinic', 'hospital_id', 'clinic_id', 'rating', 'review_count', 'status', 'user']:
            validated_data.pop(forbidden, None)

        first_n = validated_data.get('first_name', '').strip()
        last_n = validated_data.get('last_name', '').strip()
        if (first_n or last_n) and not validated_data.get('name'):
            validated_data['name'] = f"Dr. {first_n} {last_n}".strip()

        quals = validated_data.get('qualifications')
        if quals and not validated_data.get('education'):
            validated_data['education'] = ', '.join(quals) if isinstance(quals, list) else str(quals)

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

        # Create or link User account if username, email, or password provided
        user_login = (username or email or '').strip().lower()
        if user_login:
            from apps.accounts.models import User, UserRole
            user_email = user_login if '@' in user_login else f"{user_login}@meetadr.ae"
            matched_user = User.objects.filter(email__iexact=user_email).first()
            if matched_user:
                if matched_user.role != UserRole.DOCTOR:
                    raise serializers.ValidationError({"username": "A user with this username/email already exists."})
                if password:
                    matched_user.set_password(password)
                    matched_user.save()
                validated_data['user'] = matched_user
            else:
                doctor_user = User.objects.create(
                    email=user_email,
                    name=validated_data.get('name', 'Doctor'),
                    role=UserRole.DOCTOR,
                    is_active=True,
                )
                if password:
                    doctor_user.set_password(password)
                    doctor_user.save()
                validated_data['user'] = doctor_user

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
        days = validated_data.pop('available_days', None)
        slots = validated_data.pop('standard_slots', None)
        slot_duration = validated_data.pop('slot_duration_minutes', None)

        schedule = getattr(instance, 'schedule', None)
        if schedule:
            if days is not None:
                schedule.available_days = days
            if slots is not None:
                schedule.standard_slots = slots
            if slot_duration is not None:
                schedule.slot_duration_minutes = slot_duration
            schedule.save()
        elif days is not None or slots is not None:
            DoctorSchedule.objects.create(
                doctor=instance,
                available_days=days if days is not None else DEFAULT_AVAILABLE_DAYS,
                standard_slots=slots if slots is not None else DEFAULT_STANDARD_SLOTS,
                slot_duration_minutes=slot_duration or 30
            )

        return super().update(instance, validated_data)

class FacilityDoctorStatusSerializer(serializers.Serializer):
    """Payload to toggle or update a doctor's Active / Deactivated status."""
    status = serializers.ChoiceField(
        choices=FacilityStatus.choices,
        required=True
    )
