"""Appointment Serializers for Booking and Management."""
from rest_framework import serializers
from apps.appointments.models import Appointment, AppointmentStatus, DoctorReview, FacilityReview
from apps.doctors.models import Doctor
from apps.facilities.models import Hospital, Clinic

class DoctorReviewCreateSerializer(serializers.Serializer):
    """Payload serializer for submitting post-consultation doctor review."""
    rating = serializers.IntegerField(required=True)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')

    def validate_rating(self, value):
        initial_val = self.initial_data.get('rating')
        if isinstance(initial_val, (float, bool)):
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        if isinstance(initial_val, str) and ('.' in initial_val or not initial_val.isdigit()):
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_comment(self, value):
        if value and len(value) > 1000:
            raise serializers.ValidationError("Comment cannot exceed 1000 characters.")
        return value.strip() if value else ''

class DoctorReviewSummarySerializer(serializers.ModelSerializer):
    """Nested review summary for appointment payloads."""
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%SZ', read_only=True)

    class Meta:
        model = DoctorReview
        fields = ['id', 'rating', 'comment', 'created_at', 'createdAt']

class DoctorReviewDetailSerializer(serializers.ModelSerializer):
    """Private review serializer for appointment inspection and confirmation."""
    appointment_id = serializers.CharField(read_only=True)
    appointmentId = serializers.CharField(source='appointment_id', read_only=True)
    doctor_id = serializers.CharField(read_only=True)
    doctorId = serializers.CharField(source='doctor_id', read_only=True)
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    doctorName = serializers.CharField(source='doctor.name', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%SZ', read_only=True)

    class Meta:
        model = DoctorReview
        fields = [
            'id',
            'appointment_id',
            'appointmentId',
            'doctor_id',
            'doctorId',
            'doctor_name',
            'doctorName',
            'rating',
            'comment',
            'created_at',
            'createdAt',
        ]


class FacilityReviewCreateSerializer(serializers.Serializer):
    """Payload serializer for submitting post-consultation hospital/clinic review."""
    rating = serializers.IntegerField(required=True)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')

    def validate_rating(self, value):
        initial_val = self.initial_data.get('rating')
        if isinstance(initial_val, (float, bool)):
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        if isinstance(initial_val, str) and ('.' in initial_val or not initial_val.isdigit()):
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_comment(self, value):
        if value and len(value) > 1000:
            raise serializers.ValidationError("Comment cannot exceed 1000 characters.")
        return value.strip() if value else ''


class FacilityReviewSummarySerializer(serializers.ModelSerializer):
    """Nested facility review summary for appointment payloads."""
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%SZ', read_only=True)

    class Meta:
        model = FacilityReview
        fields = ['id', 'rating', 'comment', 'created_at', 'createdAt']


class FacilityReviewDetailSerializer(serializers.ModelSerializer):
    """Facility review detail serializer."""
    appointment_id = serializers.CharField(read_only=True)
    appointmentId = serializers.CharField(source='appointment_id', read_only=True)
    facility_name = serializers.SerializerMethodField()
    facilityName = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%SZ', read_only=True)

    class Meta:
        model = FacilityReview
        fields = [
            'id',
            'appointment_id',
            'appointmentId',
            'facility_name',
            'facilityName',
            'rating',
            'comment',
            'created_at',
            'createdAt',
        ]

    def get_facility_name(self, obj):
        if obj.hospital:
            return obj.hospital.name
        if obj.clinic:
            return obj.clinic.name
        return ''

    def get_facilityName(self, obj):
        return self.get_facility_name(obj)


class AppointmentCreateSerializer(serializers.Serializer):
    """Payload serializer for creating an appointment."""
    doctor_id = serializers.UUIDField(required=True)
    date = serializers.DateField(required=True)
    time_slot = serializers.CharField(max_length=64, required=True)
    dependent_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    patient_phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')

class AppointmentCancelSerializer(serializers.Serializer):
    """Payload serializer for cancelling an appointment."""
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default='Cancelled by user')

class AppointmentStatusUpdateSerializer(serializers.Serializer):
    """Payload serializer for updating appointment status."""
    status = serializers.ChoiceField(choices=[
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED
    ])

class AppointmentDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive, frontend-compatible appointment representation.
    Supports both snake_case and camelCase field access.
    """
    patientId = serializers.SerializerMethodField()
    patientName = serializers.CharField(source='patient_name_snapshot', read_only=True)
    patientPhone = serializers.CharField(source='patient_phone_snapshot', read_only=True)
    patientMobile = serializers.CharField(source='patient_phone_snapshot', read_only=True)
    patientEmail = serializers.CharField(source='patient_email_snapshot', read_only=True)
    
    doctorId = serializers.SerializerMethodField()
    doctorName = serializers.CharField(source='doctor.name', read_only=True)
    doctorPhoto = serializers.CharField(source='doctor.photo', read_only=True)
    
    hospitalId = serializers.SerializerMethodField()
    clinicId = serializers.SerializerMethodField()
    providerName = serializers.SerializerMethodField()
    facilityName = serializers.SerializerMethodField()
    hospitalName = serializers.SerializerMethodField()
    
    specialty = serializers.CharField(source='specialty_snapshot', read_only=True)
    location = serializers.CharField(source='doctor.location', read_only=True)
    
    time = serializers.CharField(source='time_slot', read_only=True)
    timeSlot = serializers.CharField(source='time_slot', read_only=True)
    
    cancelReason = serializers.CharField(source='cancel_reason', read_only=True)
    cancelledBy = serializers.CharField(source='cancelled_by_role', read_only=True)
    cancelledByName = serializers.SerializerMethodField()
    
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%SZ', read_only=True)
    is_dependent = serializers.SerializerMethodField()
    dependent_id = serializers.SerializerMethodField()
    is_reviewed = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    is_doctor_reviewed = serializers.SerializerMethodField()
    is_facility_reviewed = serializers.SerializerMethodField()
    doctor_review = serializers.SerializerMethodField()
    facility_review = serializers.SerializerMethodField()
    isDoctorReviewed = serializers.SerializerMethodField()
    isFacilityReviewed = serializers.SerializerMethodField()
    doctorReview = serializers.SerializerMethodField()
    facilityReview = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id',
            'date',
            'status',
            'notes',
            'created_at',
            # Snake_case fields
            'patient_name_snapshot',
            'patient_phone_snapshot',
            'patient_email_snapshot',
            'specialty_snapshot',
            'time_slot',
            'cancel_reason',
            'cancelled_by_role',
            'cancelled_at',
            'is_dependent',
            'dependent_id',
            'is_reviewed',
            'review',
            'is_doctor_reviewed',
            'is_facility_reviewed',
            'doctor_review',
            'facility_review',
            # Frontend camelCase aliases
            'patientId',
            'patientName',
            'patientPhone',
            'patientMobile',
            'patientEmail',
            'doctorId',
            'doctorName',
            'doctorPhoto',
            'hospitalId',
            'clinicId',
            'providerName',
            'facilityName',
            'hospitalName',
            'specialty',
            'location',
            'time',
            'timeSlot',
            'cancelReason',
            'cancelledBy',
            'cancelledByName',
            'createdAt',
            'isDoctorReviewed',
            'isFacilityReviewed',
            'doctorReview',
            'facilityReview',
        ]

    def get_patientId(self, obj):
        if obj.dependent_id:
            return str(obj.dependent_id)
        if obj.patient_profile_id:
            return str(obj.patient_profile_id)
        return str(obj.booked_by_id)

    def get_doctorId(self, obj):
        return str(obj.doctor_id)

    def get_hospitalId(self, obj):
        return str(obj.hospital_id) if obj.hospital_id else None

    def get_clinicId(self, obj):
        return str(obj.clinic_id) if obj.clinic_id else None

    def get_providerName(self, obj):
        if obj.hospital:
            return obj.hospital.name
        if obj.clinic:
            return obj.clinic.name
        return ''

    def get_facilityName(self, obj):
        return self.get_providerName(obj)

    def get_hospitalName(self, obj):
        return self.get_providerName(obj)

    def get_cancelledByName(self, obj):
        if obj.cancelled_by_user:
            return obj.cancelled_by_user.name
        return ''

    def get_is_dependent(self, obj):
        return bool(obj.dependent_id)

    def get_dependent_id(self, obj):
        return str(obj.dependent_id) if obj.dependent_id else None

    def get_is_reviewed(self, obj):
        try:
            return bool(obj.review)
        except (AttributeError, DoctorReview.DoesNotExist):
            return False

    def get_review(self, obj):
        try:
            if obj.review:
                return DoctorReviewSummarySerializer(obj.review).data
        except (AttributeError, DoctorReview.DoesNotExist):
            pass
        return None

    def get_is_doctor_reviewed(self, obj):
        return self.get_is_reviewed(obj)

    def get_isDoctorReviewed(self, obj):
        return self.get_is_reviewed(obj)

    def get_doctor_review(self, obj):
        return self.get_review(obj)

    def get_doctorReview(self, obj):
        return self.get_review(obj)

    def get_is_facility_reviewed(self, obj):
        try:
            return bool(obj.facility_review)
        except (AttributeError, FacilityReview.DoesNotExist):
            return False

    def get_isFacilityReviewed(self, obj):
        return self.get_is_facility_reviewed(obj)

    def get_facility_review(self, obj):
        try:
            if obj.facility_review:
                return FacilityReviewSummarySerializer(obj.facility_review).data
        except (AttributeError, FacilityReview.DoesNotExist):
            pass
        return None

    def get_facilityReview(self, obj):
        return self.get_facility_review(obj)

