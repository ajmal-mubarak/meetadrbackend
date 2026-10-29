"""Doctor Directory and Availability Serializers."""
from rest_framework import serializers
from apps.facilities.models import FacilityStatus
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
    available_slots = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            'id', 'name', 'name_ar', 'photo', 'specialty',
            'special_interests', 'experience_years', 'experience_text',
            'experience_text_ar', 'rating', 'review_count', 'location',
            'consultation_fee', 'status',
            'hospital_id', 'hospital_name', 'hospital_name_ar',
            'clinic_id', 'clinic_name',
            'about', 'about_ar', 'education', 'available_days', 'available_slots',
            'first_name', 'last_name', 'gender', 'department', 'qualifications',
            'country_of_origin', 'languages', 'phone_dial_code', 'contact_number', 'email'
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
        if hasattr(obj, 'schedule') and obj.schedule:
            return obj.schedule.available_days
        return []

    def get_available_slots(self, obj):
        if hasattr(obj, 'schedule') and obj.schedule:
            return obj.schedule.standard_slots
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


class AdminDoctorListSerializer(DoctorListSerializer):
    """
    Platform-wide admin serializer for Doctor management.
    Provides camelCase aliases for the AdminDoctors frontend contract while preserving
    snake_case attributes and relational facility details.
    """
    experience = serializers.SerializerMethodField()
    hospitalName = serializers.SerializerMethodField()
    clinicName = serializers.SerializerMethodField()
    hospitalId = serializers.SerializerMethodField()
    clinicId = serializers.SerializerMethodField()
    consultationFee = serializers.DecimalField(source='consultation_fee', max_digits=8, decimal_places=2, read_only=True)
    reviewCount = serializers.IntegerField(source='review_count', read_only=True)
    specialInterest = serializers.JSONField(source='special_interests', read_only=True)
    availableDays = serializers.SerializerMethodField()
    availableSlots = serializers.SerializerMethodField()
    available_slots = serializers.SerializerMethodField()

    class Meta(DoctorListSerializer.Meta):
        fields = DoctorListSerializer.Meta.fields + [
            'experience',
            'hospitalName',
            'clinicName',
            'hospitalId',
            'clinicId',
            'consultationFee',
            'reviewCount',
            'specialInterest',
            'availableDays',
            'availableSlots',
            'available_slots',
        ]

    def get_experience(self, obj):
        if obj.experience_text:
            return obj.experience_text
        return f"{obj.experience_years} years"

    def get_hospitalName(self, obj):
        return obj.hospital.name if obj.hospital else None

    def get_clinicName(self, obj):
        return obj.clinic.name if obj.clinic else None

    def get_hospitalId(self, obj):
        return str(obj.hospital_id) if obj.hospital_id else None

    def get_clinicId(self, obj):
        return str(obj.clinic_id) if obj.clinic_id else None

    def get_availableDays(self, obj):
        return self.get_available_days(obj)

    def get_availableSlots(self, obj):
        if hasattr(obj, 'schedule') and obj.schedule:
            return obj.schedule.standard_slots
        return []

    def get_available_slots(self, obj):
        return self.get_availableSlots(obj)


class AdminDoctorStatusUpdateSerializer(serializers.Serializer):
    """
    Platform administrator doctor activation/deactivation payload serializer.
    Permits strictly and exclusively the status choice field.
    """
    status = serializers.ChoiceField(choices=FacilityStatus.choices)


class AdminDoctorCreateSerializer(serializers.ModelSerializer):
    """
    Platform administrator serializer for creating new individual or facility-affiliated doctors.
    Automatically initializes a complete DoctorSchedule.
    """
    nameAr = serializers.CharField(source='name_ar', required=False, allow_blank=True)
    aboutAr = serializers.CharField(source='about_ar', required=False, allow_blank=True)
    consultationFee = serializers.DecimalField(source='consultation_fee', max_digits=8, decimal_places=2, required=False, allow_null=True)
    experienceYears = serializers.IntegerField(source='experience_years', required=False)
    hospitalId = serializers.UUIDField(required=False, allow_null=True)
    clinicId = serializers.UUIDField(required=False, allow_null=True)
    availableDays = serializers.ListField(child=serializers.CharField(), required=False)
    standardSlots = serializers.ListField(child=serializers.CharField(), required=False)
    username = serializers.CharField(required=False, write_only=True, allow_blank=True)
    password = serializers.CharField(required=False, write_only=True, allow_blank=True)
    email = serializers.CharField(required=False, write_only=True, allow_blank=True)

    class Meta:
        model = Doctor
        fields = [
            'id',
            'name',
            'name_ar',
            'nameAr',
            'photo',
            'specialty',
            'special_interests',
            'location',
            'consultation_fee',
            'consultationFee',
            'experience_years',
            'experienceYears',
            'education',
            'about',
            'about_ar',
            'aboutAr',
            'hospital',
            'clinic',
            'hospitalId',
            'clinicId',
            'availableDays',
            'standardSlots',
            'status',
            'username',
            'password',
            'email',
            'first_name',
            'last_name',
            'gender',
            'department',
            'qualifications',
            'country_of_origin',
            'languages',
            'phone_dial_code',
            'contact_number',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        hospital_id = attrs.pop('hospitalId', None)
        clinic_id = attrs.pop('clinicId', None)

        if hospital_id:
            from apps.facilities.models import Hospital
            try:
                attrs['hospital'] = Hospital.objects.get(id=hospital_id)
            except Hospital.DoesNotExist:
                raise serializers.ValidationError({'hospitalId': "Hospital does not exist."})

        if clinic_id:
            from apps.facilities.models import Clinic
            try:
                attrs['clinic'] = Clinic.objects.get(id=clinic_id)
            except Clinic.DoesNotExist:
                raise serializers.ValidationError({'clinicId': "Clinic does not exist."})

        if attrs.get('hospital') and attrs.get('clinic'):
            raise serializers.ValidationError("A doctor cannot belong to both a Hospital and a Clinic.")

        return attrs

    def create(self, validated_data):
        available_days = validated_data.pop('availableDays', None)
        standard_slots = validated_data.pop('standardSlots', None)
        username = validated_data.pop('username', None)
        password = validated_data.pop('password', None)
        email = validated_data.pop('email', None)

        facility = validated_data.get('hospital') or validated_data.get('clinic')
        facility_days = getattr(facility, 'default_available_days', None) if facility else None
        facility_slots = getattr(facility, 'default_standard_slots', None) if facility else None

        if not available_days:
            if facility_days and len(facility_days) > 0:
                available_days = list(facility_days)
            else:
                available_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        if not standard_slots:
            if facility_slots and len(facility_slots) > 0:
                standard_slots = list(facility_slots)
            else:
                standard_slots = [
                    '08:00 - 08:30', '08:30 - 09:00', '09:00 - 09:30', '09:30 - 10:00',
                    '10:00 - 10:30', '10:30 - 11:00', '11:00 - 11:30', '11:30 - 12:00',
                    '14:00 - 14:30', '14:30 - 15:00', '15:00 - 15:30', '15:30 - 16:00',
                    '16:00 - 16:30', '16:30 - 17:00'
                ]

        first_n = validated_data.get('first_name', '').strip()
        last_n = validated_data.get('last_name', '').strip()
        if (first_n or last_n) and not validated_data.get('name'):
            validated_data['name'] = f"Dr. {first_n} {last_n}".strip()

        quals = validated_data.get('qualifications')
        if quals and not validated_data.get('education'):
            validated_data['education'] = ', '.join(quals) if isinstance(quals, list) else str(quals)

        if not validated_data.get('experience_text') and validated_data.get('experience_years'):
            validated_data['experience_text'] = f"{validated_data['experience_years']} years"
            validated_data['experience_text_ar'] = f"{validated_data['experience_years']} سنوات"

        if 'rating' not in validated_data:
            validated_data['rating'] = 0.00
        if 'review_count' not in validated_data:
            validated_data['review_count'] = 0

        # Create or link User account if username or password provided
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

        doctor = super().create(validated_data)

        DoctorSchedule.objects.create(
            doctor=doctor,
            available_days=available_days,
            standard_slots=standard_slots,
            slot_duration_minutes=30
        )

        return doctor


