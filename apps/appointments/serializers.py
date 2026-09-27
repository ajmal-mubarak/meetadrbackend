"""Appointment Serializers for Booking and Management."""
from rest_framework import serializers
from apps.appointments.models import Appointment, AppointmentStatus
from apps.doctors.models import Doctor
from apps.facilities.models import Hospital, Clinic

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
