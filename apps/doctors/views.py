"""Doctor Directory, Filtering, and Slot Availability Views."""
import uuid
from datetime import datetime, date
from django.db.models import Q
from rest_framework import generics, views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound, ValidationError
from apps.doctors.models import Doctor, DoctorSchedule
from apps.facilities.models import FacilityStatus
from apps.appointments.models import Appointment, AppointmentStatus
from apps.doctors.serializers import DoctorListSerializer, DoctorDetailSerializer

class DoctorListView(generics.ListAPIView):
    """
    Public directory of accredited doctors with multi-parameter faceted filtering.
    Filters: specialty, location, hospital, clinic, practicing day, rating, search keyword.
    """
    permission_classes = [AllowAny]
    serializer_class = DoctorListSerializer

    def get_queryset(self):
        # Strict security constraint: only active doctors affiliated with active facilities
        queryset = Doctor.objects.filter(
            status=FacilityStatus.ACTIVE
        ).filter(
            Q(hospital__isnull=False, hospital__status=FacilityStatus.ACTIVE) |
            Q(clinic__isnull=False, clinic__status=FacilityStatus.ACTIVE)
        ).select_related('hospital', 'clinic', 'schedule')

        params = self.request.query_params

        # Specialty filter
        specialty = params.get('specialty')
        if specialty and specialty.lower() != 'all':
            queryset = queryset.filter(specialty__iexact=specialty.strip())

        # Location filter
        location = params.get('location')
        if location and location.lower() != 'all':
            queryset = queryset.filter(location__icontains=location.strip())

        # Hospital affiliation filter (safely validated for valid UUID)
        hospital_id = params.get('hospital_id') or params.get('hospital')
        if hospital_id and hospital_id.lower() != 'all':
            try:
                valid_uuid = uuid.UUID(str(hospital_id).strip())
                queryset = queryset.filter(hospital_id=valid_uuid)
            except (ValueError, AttributeError):
                return queryset.none()

        # Clinic affiliation filter (safely validated for valid UUID)
        clinic_id = params.get('clinic_id') or params.get('clinic')
        if clinic_id and clinic_id.lower() != 'all':
            try:
                valid_uuid = uuid.UUID(str(clinic_id).strip())
                queryset = queryset.filter(clinic_id=valid_uuid)
            except (ValueError, AttributeError):
                return queryset.none()

        # Minimum rating filter
        min_rating = params.get('min_rating') or params.get('rating')
        if min_rating:
            try:
                rating_val = float(min_rating)
                queryset = queryset.filter(rating__gte=rating_val)
            except ValueError:
                pass

        # Practicing day filter (e.g. 'Monday', 'Tuesday')
        day = params.get('day') or params.get('practicing_day')
        if day and day.lower() != 'all':
            day_clean = day.capitalize().strip()
            queryset = queryset.filter(schedule__available_days__icontains=day_clean)

        # Search keyword
        search = params.get('search')
        if search:
            q = search.strip()
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(name_ar__icontains=q) |
                Q(specialty__icontains=q) |
                Q(location__icontains=q) |
                Q(hospital__name__icontains=q) |
                Q(clinic__name__icontains=q) |
                Q(about__icontains=q)
            ).distinct()

        return queryset.order_by('-rating', 'name')

class DoctorDetailView(generics.RetrieveAPIView):
    """Detailed doctor profile with full facility info and practicing schedule."""
    permission_classes = [AllowAny]
    serializer_class = DoctorDetailSerializer

    def get_queryset(self):
        return Doctor.objects.filter(
            status=FacilityStatus.ACTIVE
        ).filter(
            Q(hospital__isnull=False, hospital__status=FacilityStatus.ACTIVE) |
            Q(clinic__isnull=False, clinic__status=FacilityStatus.ACTIVE)
        ).select_related('hospital', 'clinic', 'schedule')

class DoctorAvailabilityView(views.APIView):
    """
    Dynamic consultation slot availability calculator for a specific date.
    Eliminates race condition collisions by cross-referencing doctor schedule
    against currently booked, non-cancelled appointments.
    Strictly requires both Doctor AND affiliated Hospital/Clinic to be ACTIVE.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        doctor = Doctor.objects.select_related('schedule').filter(
            id=pk,
            status=FacilityStatus.ACTIVE
        ).filter(
            Q(hospital__isnull=False, hospital__status=FacilityStatus.ACTIVE) |
            Q(clinic__isnull=False, clinic__status=FacilityStatus.ACTIVE)
        ).first()

        if not doctor:
            raise NotFound("Doctor not found or not active.")

        date_str = request.query_params.get('date')
        if not date_str:
            raise ValidationError({'date': "Query parameter 'date' (YYYY-MM-DD) is required."})

        try:
            target_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
        except ValueError:
            raise ValidationError({'date': "Invalid date format. Expected YYYY-MM-DD."})

        day_name = target_date.strftime('%A')

        # Check if doctor has an active schedule
        schedule = getattr(doctor, 'schedule', None)
        if not schedule or day_name not in schedule.available_days:
            return Response({
                'doctor_id': str(doctor.id),
                'doctor_name': doctor.name,
                'date': str(target_date),
                'day': day_name,
                'available': False,
                'total_slots': 0,
                'slots': [],
                'booked_slots': []
            }, status=status.HTTP_200_OK)

        # Standard configured slots
        standard_slots = schedule.standard_slots or []

        # Find existing active bookings for this doctor on target date
        booked_slots = list(
            Appointment.objects.filter(
                doctor=doctor,
                date=target_date
            ).exclude(
                status=AppointmentStatus.CANCELLED
            ).values_list('time_slot', flat=True)
        )

        # Available slots = standard configured slots minus booked slots
        available_slots = [slot for slot in standard_slots if slot not in booked_slots]

        return Response({
            'doctor_id': str(doctor.id),
            'doctor_name': doctor.name,
            'date': str(target_date),
            'day': day_name,
            'available': True,
            'total_slots': len(standard_slots),
            'slots': available_slots,
            'booked_slots': booked_slots
        }, status=status.HTTP_200_OK)
