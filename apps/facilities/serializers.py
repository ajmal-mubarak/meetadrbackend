"""Hospital, Clinic, Department, and Medical Conditions Serializers."""
from django.db.models import Avg, Sum, Count
from rest_framework import serializers
from apps.facilities.models import Hospital, Clinic, FacilityDepartment, FacilityStatus
from apps.doctors.models import Doctor

class FacilityDepartmentSerializer(serializers.ModelSerializer):
    """Clinical department within an accredited hospital."""
    class Meta:
        model = FacilityDepartment
        fields = ['id', 'name', 'head_of_department', 'bed_capacity']

class PublicDoctorSummarySerializer(serializers.ModelSerializer):
    """Safe, public doctor profile card for facility doctor rosters."""
    class Meta:
        model = Doctor
        fields = [
            'id', 'name', 'name_ar', 'photo', 'specialty',
            'experience_years', 'experience_text', 'experience_text_ar',
            'rating', 'review_count', 'consultation_fee'
        ]

class HospitalListSerializer(serializers.ModelSerializer):
    """Public list serializer for accredited hospitals."""
    doctor_count = serializers.SerializerMethodField()
    specialties = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()

    class Meta:
        model = Hospital
        fields = [
            'id', 'name', 'name_ar', 'photo', 'location',
            'address', 'address_ar', 'phone', 'operating_hours',
            'operating_hours_ar', 'about', 'about_ar',
            'emergency_available', 'status', 'doctor_count', 'specialties',
            'avg_rating', 'total_reviews',
        ]

    def get_doctor_count(self, obj):
        if hasattr(obj, 'doctor_count'):
            return obj.doctor_count
        return obj.doctors.filter(status=FacilityStatus.ACTIVE).count()

    def get_specialties(self, obj):
        # Use in-memory prefetched doctors if available to eliminate per-facility SQL query
        if hasattr(obj, '_prefetched_objects_cache') and 'doctors' in obj._prefetched_objects_cache:
            return sorted(list(set(
                doc.specialty for doc in obj.doctors.all()
                if doc.status == FacilityStatus.ACTIVE
            )))
        return list(
            obj.doctors.filter(status=FacilityStatus.ACTIVE)
            .values_list('specialty', flat=True)
            .distinct()
        )

    def get_avg_rating(self, obj):
        """
        Compute real average rating from verified patient FacilityReview records.
        Returns None if no verified reviews exist yet.
        """
        agg = obj.reviews.aggregate(
            avg_rating=Avg('rating'),
            count=Count('id')
        )
        count = agg.get('count') or 0
        if count == 0:
            return None
        avg_rating = agg.get('avg_rating') or 0.0
        return round(float(avg_rating), 1)

    def get_total_reviews(self, obj):
        return obj.reviews.count()

class HospitalDetailSerializer(HospitalListSerializer):
    """Detailed hospital profile including clinical departments and affiliated doctors."""
    departments = FacilityDepartmentSerializer(many=True, read_only=True)
    doctors = serializers.SerializerMethodField()

    class Meta(HospitalListSerializer.Meta):
        fields = HospitalListSerializer.Meta.fields + ['departments', 'doctors']

    def get_doctors(self, obj):
        active_doctors = obj.doctors.filter(status=FacilityStatus.ACTIVE)
        return PublicDoctorSummarySerializer(active_doctors, many=True).data

class ClinicListSerializer(serializers.ModelSerializer):
    """Public list serializer for specialized outpatient clinics."""
    doctor_count = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()

    class Meta:
        model = Clinic
        fields = [
            'id', 'name', 'name_ar', 'photo', 'location',
            'address', 'address_ar', 'primary_specialty',
            'phone', 'operating_hours', 'operating_hours_ar',
            'about', 'about_ar', 'status', 'doctor_count',
            'avg_rating', 'total_reviews',
        ]

    def get_doctor_count(self, obj):
        if hasattr(obj, 'doctor_count'):
            return obj.doctor_count
        return obj.doctors.filter(status=FacilityStatus.ACTIVE).count()

    def get_avg_rating(self, obj):
        agg = obj.reviews.aggregate(
            avg_rating=Avg('rating'),
            count=Count('id')
        )
        count = agg.get('count') or 0
        if count == 0:
            return None
        avg_rating = agg.get('avg_rating') or 0.0
        return round(float(avg_rating), 1)

    def get_total_reviews(self, obj):
        return obj.reviews.count()

class ClinicDetailSerializer(ClinicListSerializer):
    """Detailed clinic profile including affiliated active doctors."""
    doctors = serializers.SerializerMethodField()

    class Meta(ClinicListSerializer.Meta):
        fields = ClinicListSerializer.Meta.fields + ['doctors']

    def get_doctors(self, obj):
        active_doctors = obj.doctors.filter(status=FacilityStatus.ACTIVE)
        return PublicDoctorSummarySerializer(active_doctors, many=True).data

class HealthConditionSerializer(serializers.Serializer):
    """Medical condition representation in A-Z public directory."""
    id = serializers.CharField()
    letter = serializers.CharField()
    name = serializers.CharField()
    specialist = serializers.CharField()
    specialty = serializers.CharField()
    specialtyQuery = serializers.CharField(source='specialty', required=False)
    description = serializers.CharField()
    symptoms = serializers.ListField(child=serializers.CharField(), required=False)
    causes = serializers.ListField(child=serializers.CharField(), required=False)
    risk_factors = serializers.ListField(child=serializers.CharField(), required=False)
    riskFactors = serializers.ListField(child=serializers.CharField(), source='risk_factors', required=False)
    prevention = serializers.ListField(child=serializers.CharField(), required=False)
    management = serializers.ListField(child=serializers.CharField(), required=False)
