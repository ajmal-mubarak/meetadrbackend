"""Hospital, Clinic, Department, and Medical Conditions Public Discovery Views."""
from django.db.models import Q, Count
from rest_framework import generics, views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor
from apps.facilities.serializers import (
    HospitalListSerializer,
    HospitalDetailSerializer,
    ClinicListSerializer,
    ClinicDetailSerializer,
    HealthConditionSerializer
)
from apps.facilities.conditions_data import (
    filter_conditions,
    get_condition_by_id,
    get_conditions_alphabet
)

class HospitalListView(generics.ListAPIView):
    """
    Public directory of accredited medical hospitals with faceted filtering.
    Filters: location, emergency_available, specialty, search keyword.
    """
    permission_classes = [AllowAny]
    serializer_class = HospitalListSerializer

    def get_queryset(self):
        queryset = Hospital.objects.filter(
            status=FacilityStatus.ACTIVE
        ).annotate(
            doctor_count=Count(
                'doctors',
                filter=Q(doctors__status=FacilityStatus.ACTIVE),
                distinct=True
            )
        ).prefetch_related('doctors')

        # Filter by location
        location = self.request.query_params.get('location')
        if location and location.lower() != 'all':
            queryset = queryset.filter(location__icontains=location.strip())

        # Filter by 24/7 Emergency Availability
        emergency = self.request.query_params.get('emergency_available')
        if emergency is not None:
            if emergency.lower() in ['true', '1', 'yes']:
                queryset = queryset.filter(emergency_available=True)
            elif emergency.lower() in ['false', '0', 'no']:
                queryset = queryset.filter(emergency_available=False)

        # Filter by Specialty presence
        specialty = self.request.query_params.get('specialty')
        if specialty and specialty.lower() != 'all':
            queryset = queryset.filter(
                doctors__specialty__iexact=specialty.strip(),
                doctors__status=FacilityStatus.ACTIVE
            ).distinct()

        # Keyword search
        search = self.request.query_params.get('search')
        if search:
            q = search.strip()
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(name_ar__icontains=q) |
                Q(location__icontains=q) |
                Q(address__icontains=q) |
                Q(about__icontains=q)
            ).distinct()

        return queryset.order_by('name')

class HospitalDetailView(generics.RetrieveAPIView):
    """Detailed hospital profile with clinical departments and affiliated doctors."""
    permission_classes = [AllowAny]
    serializer_class = HospitalDetailSerializer

    def get_queryset(self):
        return Hospital.objects.filter(
            status=FacilityStatus.ACTIVE
        ).annotate(
            doctor_count=Count(
                'doctors',
                filter=Q(doctors__status=FacilityStatus.ACTIVE),
                distinct=True
            )
        ).prefetch_related('departments', 'doctors')

class ClinicListView(generics.ListAPIView):
    """
    Public directory of specialized outpatient clinics with faceted filtering.
    Filters: location, specialty, search keyword.
    """
    permission_classes = [AllowAny]
    serializer_class = ClinicListSerializer

    def get_queryset(self):
        queryset = Clinic.objects.filter(
            status=FacilityStatus.ACTIVE
        ).annotate(
            doctor_count=Count(
                'doctors',
                filter=Q(doctors__status=FacilityStatus.ACTIVE),
                distinct=True
            )
        ).prefetch_related('doctors')

        # Filter by location
        location = self.request.query_params.get('location')
        if location and location.lower() != 'all':
            queryset = queryset.filter(location__icontains=location.strip())

        # Filter by primary specialty
        specialty = self.request.query_params.get('specialty')
        if specialty and specialty.lower() != 'all':
            queryset = queryset.filter(primary_specialty__iexact=specialty.strip())

        # Keyword search
        search = self.request.query_params.get('search')
        if search:
            q = search.strip()
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(name_ar__icontains=q) |
                Q(location__icontains=q) |
                Q(primary_specialty__icontains=q) |
                Q(about__icontains=q)
            ).distinct()

        return queryset.order_by('name')

class ClinicDetailView(generics.RetrieveAPIView):
    """Detailed clinic profile with affiliated doctors roster."""
    permission_classes = [AllowAny]
    serializer_class = ClinicDetailSerializer

    def get_queryset(self):
        return Clinic.objects.filter(
            status=FacilityStatus.ACTIVE
        ).annotate(
            doctor_count=Count(
                'doctors',
                filter=Q(doctors__status=FacilityStatus.ACTIVE),
                distinct=True
            )
        ).prefetch_related('doctors')

class SpecialtyListView(views.APIView):
    """Returns list of distinct active medical specialties available across the platform."""
    permission_classes = [AllowAny]

    def get(self, request):
        doc_specialties = (
            Doctor.objects.filter(
                status=FacilityStatus.ACTIVE
            ).filter(
                Q(hospital__isnull=False, hospital__status=FacilityStatus.ACTIVE) |
                Q(clinic__isnull=False, clinic__status=FacilityStatus.ACTIVE)
            )
            .values_list('specialty', flat=True)
            .distinct()
        )
        clinic_specialties = (
            Clinic.objects.filter(status=FacilityStatus.ACTIVE)
            .values_list('primary_specialty', flat=True)
            .distinct()
        )

        all_specialties = sorted(list(set(list(doc_specialties) + list(clinic_specialties))))
        return Response({'specialties': all_specialties}, status=status.HTTP_200_OK)

class ConditionListView(views.APIView):
    """Public A-Z Health Conditions directory with symptoms and specialty mappings."""
    permission_classes = [AllowAny]

    def get(self, request):
        letter = request.query_params.get('letter')
        search = request.query_params.get('search')

        results = filter_conditions(letter=letter, search=search)
        alphabet = get_conditions_alphabet()

        serializer = HealthConditionSerializer(results, many=True)
        return Response({
            'letters': ['All'] + alphabet,
            'count': len(results),
            'results': serializer.data
        }, status=status.HTTP_200_OK)

class ConditionDetailView(views.APIView):
    """Detailed medical condition information by unique slug ID."""
    permission_classes = [AllowAny]

    def get(self, request, condition_id):
        cond = get_condition_by_id(condition_id)
        if not cond:
            raise NotFound("Health condition not found.")

        serializer = HealthConditionSerializer(cond)
        return Response(serializer.data, status=status.HTTP_200_OK)
