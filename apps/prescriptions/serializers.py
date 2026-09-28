"""Prescription and Medication Serializers."""
from rest_framework import serializers
from apps.prescriptions.models import Prescription, PrescriptionMedication, PrescriptionStatus


class PrescriptionMedicationSerializer(serializers.ModelSerializer):
    """Serializer for individual prescribed medication items."""
    medication_name = serializers.CharField(max_length=255, required=True, allow_blank=False)
    dosage = serializers.CharField(max_length=128, required=True, allow_blank=False)
    frequency = serializers.CharField(max_length=128, required=True, allow_blank=False)
    duration = serializers.CharField(max_length=128, required=True, allow_blank=False)
    instructions = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = PrescriptionMedication
        fields = [
            'id',
            'medication_name',
            'dosage',
            'frequency',
            'duration',
            'instructions',
        ]
        read_only_fields = ['id']


class PrescriptionReadSerializer(serializers.ModelSerializer):
    """Structured clinical prescription serializer for patient and provider reads."""
    appointment_id = serializers.UUIDField(source='appointment.id', read_only=True)
    doctor_id = serializers.UUIDField(source='doctor.id', read_only=True)
    doctor_name = serializers.SerializerMethodField()
    doctor_specialization = serializers.CharField(source='doctor.specialization', read_only=True)
    facility_name = serializers.SerializerMethodField()
    patient_id = serializers.UUIDField(source='patient.id', read_only=True)
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    is_dependent = serializers.SerializerMethodField()
    dependent = serializers.SerializerMethodField()
    medications = PrescriptionMedicationSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = [
            'id',
            'appointment_id',
            'doctor_id',
            'doctor_name',
            'doctor_specialization',
            'facility_name',
            'patient_id',
            'patient_name',
            'is_dependent',
            'dependent',
            'diagnosis',
            'instructions',
            'status',
            'issued_at',
            'medications',
        ]
        read_only_fields = fields

    def get_doctor_name(self, obj) -> str:
        return f"Dr. {obj.doctor.name}"

    def get_facility_name(self, obj) -> str:
        facility = obj.doctor.hospital or obj.doctor.clinic
        return getattr(facility, 'name', '')

    def get_is_dependent(self, obj) -> bool:
        return bool(obj.appointment and obj.appointment.dependent_id)

    def get_dependent(self, obj):
        if not (obj.appointment and obj.appointment.dependent):
            return None
        dep = obj.appointment.dependent
        return {
            'id': str(dep.id),
            'name': dep.name,
            'relationship': getattr(dep, 'relation', getattr(dep, 'relationship', '')),
            'relation': getattr(dep, 'relation', ''),
            'date_of_birth': str(dep.dob) if getattr(dep, 'dob', None) else '',
            'dob': str(dep.dob) if getattr(dep, 'dob', None) else '',
            'gender': dep.gender,
        }


class PrescriptionCreateSerializer(serializers.Serializer):
    """
    Payload serializer for issuing a clinical prescription.
    
    Security Invariant:
    Doctor identity, patient identity, and facility are NEVER accepted from client.
    They are strictly derived on the server from the authenticated doctor and appointment.
    """
    appointment_id = serializers.UUIDField(required=True)
    diagnosis = serializers.CharField(required=True, allow_blank=False, min_length=2)
    instructions = serializers.CharField(required=False, allow_blank=True, default='')
    medications = PrescriptionMedicationSerializer(many=True, required=True)

    def validate_medications(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one medication item must be prescribed.")
        return value
