"""Doctor Directory and Availability Serializers."""
from rest_framework import serializers
from apps.doctors.models import Doctor, DoctorSchedule
from apps.facilities.serializers import HospitalListSerializer, ClinicListSerializer

class DoctorScheduleSerializer(serializers.ModelSerializer):
    """Doctor availability schedule and standard slot duration."""
    class Meta:
        model = DoctorSchedule
        fields = ['available_days', 'standard_slots', 'slot_duration_minutes']

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
