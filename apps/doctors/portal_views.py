"""Doctor Portal Operations Views: Schedule, Dashboard KPIs, and Patient Directory."""
from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.permissions import IsDoctor
from apps.doctors.models import DoctorSchedule
from apps.doctors.serializers import (
    DoctorScheduleSerializer,
    DoctorScheduleUpdateSerializer,
    VALID_WEEKDAYS,
)
from apps.appointments.models import Appointment, AppointmentStatus
from apps.audit.utils import log_audit_event

DEFAULT_AVAILABLE_DAYS = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
]

DEFAULT_STANDARD_SLOTS = [
    '09:00 - 09:30',
    '09:30 - 10:00',
    '10:00 - 10:30',
    '10:30 - 11:00',
    '11:00 - 11:30',
    '11:30 - 12:00',
    '14:00 - 14:30',
    '14:30 - 15:00',
    '15:00 - 15:30',
    '15:30 - 16:00',
    '16:00 - 16:30',
    '16:30 - 17:00',
]


def _get_authenticated_doctor(request):
    """Strictly resolve accredited Doctor profile from authenticated user."""
    if not (request.user and request.user.is_authenticated and hasattr(request.user, 'doctor_profile') and request.user.doctor_profile):
        raise PermissionDenied("Authenticated user is not linked to an active doctor profile.")
    return request.user.doctor_profile


class DoctorScheduleManageView(views.APIView):
    """
    Manage doctor practicing schedule and standard 30-min consultation slots.
    GET auto-provisions default schedule if none exists yet.
    PUT/PATCH updates practicing days, slots, and slot duration.
    """
    permission_classes = [IsAuthenticated, IsDoctor]

    def get(self, request):
        doctor = _get_authenticated_doctor(request)
        schedule, _ = DoctorSchedule.objects.get_or_create(
            doctor=doctor,
            defaults={
                'available_days': DEFAULT_AVAILABLE_DAYS,
                'standard_slots': DEFAULT_STANDARD_SLOTS,
                'slot_duration_minutes': 30,
            }
        )
        serializer = DoctorScheduleSerializer(schedule)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        return self._update_schedule(request, partial=False)

    def patch(self, request):
        return self._update_schedule(request, partial=True)

    def _update_schedule(self, request, partial=False):
        doctor = _get_authenticated_doctor(request)
        schedule, _ = DoctorSchedule.objects.get_or_create(
            doctor=doctor,
            defaults={
                'available_days': DEFAULT_AVAILABLE_DAYS,
                'standard_slots': DEFAULT_STANDARD_SLOTS,
                'slot_duration_minutes': 30,
            }
        )

        serializer = DoctorScheduleUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            locked_schedule = DoctorSchedule.objects.select_for_update().get(id=schedule.id)

            if 'available_days' in data:
                locked_schedule.available_days = data['available_days']
            elif not partial:
                locked_schedule.available_days = []

            if 'standard_slots' in data:
                locked_schedule.standard_slots = data['standard_slots']
            elif not partial:
                locked_schedule.standard_slots = []

            if 'slot_duration_minutes' in data:
                locked_schedule.slot_duration_minutes = data['slot_duration_minutes']
            elif not partial:
                locked_schedule.slot_duration_minutes = 30

            locked_schedule.save()

        log_audit_event(
            actor=request.user,
            action='DOCTOR_SCHEDULE_UPDATED',
            target_model='DoctorSchedule',
            target_id=str(locked_schedule.id),
            change_summary={
                'doctor_id': str(doctor.id),
                'schedule_id': str(locked_schedule.id),
                'available_days_count': len(locked_schedule.available_days),
                'standard_slots_count': len(locked_schedule.standard_slots),
            },
            request=request
        )

        return Response(DoctorScheduleSerializer(locked_schedule).data, status=status.HTTP_200_OK)


class DoctorDashboardView(views.APIView):
    """
    Unified doctor clinical KPI metrics, weekly workload trend, and upcoming appointments.
    Strictly scoped to consultations of the authenticated doctor.
    """
    permission_classes = [IsAuthenticated, IsDoctor]

    def get(self, request):
        doctor = _get_authenticated_doctor(request)
        today = timezone.localdate()

        # Aggregate core appointment metrics in single query
        stats_agg = Appointment.objects.filter(doctor=doctor).aggregate(
            total=Count('id'),
            today=Count('id', filter=Q(date=today)),
            completed=Count('id', filter=Q(status=AppointmentStatus.COMPLETED)),
            cancelled=Count('id', filter=Q(status=AppointmentStatus.CANCELLED)),
            pending=Count('id', filter=Q(status=AppointmentStatus.PENDING)),
            confirmed=Count('id', filter=Q(status=AppointmentStatus.CONFIRMED)),
        )

        total_appts = stats_agg['total'] or 0
        today_appts = stats_agg['today'] or 0
        completed_appts = stats_agg['completed'] or 0
        cancelled_appts = stats_agg['cancelled'] or 0
        pending_appts = stats_agg['pending'] or 0
        confirmed_appts = stats_agg['confirmed'] or 0

        # Safe completion rate with zero-division safeguard
        completion_rate = round((completed_appts / total_appts) * 100, 2) if total_appts > 0 else 0.0

        # Reporting gross consultation fee earned from completed visits
        consultation_fee = doctor.consultation_fee or Decimal('0.00')
        total_revenue = float(Decimal(completed_appts) * consultation_fee)

        # Unique treated patients count (primary + dependents)
        primary_count = Appointment.objects.filter(
            doctor=doctor,
            patient_profile__isnull=False,
            dependent__isnull=True
        ).values('patient_profile_id').distinct().count()

        dependent_count = Appointment.objects.filter(
            doctor=doctor,
            dependent__isnull=False
        ).values('dependent_id').distinct().count()

        active_patients = primary_count + dependent_count

        # Weekly trend for 7 rolling days up to today
        start_date = today - timedelta(days=6)
        day_counts = Appointment.objects.filter(
            doctor=doctor,
            date__range=(start_date, today)
        ).values('date').annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(status=AppointmentStatus.COMPLETED))
        )
        day_map = {item['date']: item for item in day_counts}
        weekly_trend = []
        for i in range(7):
            d = start_date + timedelta(days=i)
            item = day_map.get(d, {'total': 0, 'completed': 0})
            weekly_trend.append({
                'date': d.strftime('%Y-%m-%d'),
                'day': d.strftime('%a'),
                'total': item['total'],
                'completed': item['completed'],
            })

        # Top 5 upcoming active consultations
        upcoming_qs = Appointment.objects.filter(
            doctor=doctor,
            date__gte=today,
            status__in=[AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING]
        ).select_related(
            'patient_profile__user',
            'dependent'
        ).order_by('date', 'time_slot')[:5]

        upcoming = []
        for a in upcoming_qs:
            if a.dependent:
                p_name = a.patient_name_snapshot or a.dependent.name
            elif a.patient_profile and hasattr(a.patient_profile, 'user'):
                p_name = a.patient_name_snapshot or a.patient_profile.user.name
            else:
                p_name = a.patient_name_snapshot or "Patient"

            upcoming.append({
                'id': str(a.id),
                'patientName': p_name,
                'patient_name': p_name,
                'date': str(a.date),
                'timeSlot': a.time_slot,
                'time_slot': a.time_slot,
                'status': a.status,
                'notes': a.notes or '',
            })

        return Response({
            'stats': {
                'totalAppointments': total_appts,
                'total_appointments': total_appts,
                'todayAppointments': today_appts,
                'today_appointments': today_appts,
                'completedAppointments': completed_appts,
                'completed_appointments': completed_appts,
                'cancelledAppointments': cancelled_appts,
                'cancelled_appointments': cancelled_appts,
                'pendingAppointments': pending_appts,
                'pending_appointments': pending_appts,
                'confirmedAppointments': confirmed_appts,
                'confirmed_appointments': confirmed_appts,
                'completionRate': completion_rate,
                'completion_rate': completion_rate,
                'totalRevenue': total_revenue,
                'total_revenue': total_revenue,
                'activePatients': active_patients,
                'active_patients': active_patients,
                'rating': float(doctor.rating),
                'reviewCount': doctor.review_count,
                'review_count': doctor.review_count,
            },
            'weeklyTrend': weekly_trend,
            'weekly_trend': weekly_trend,
            'upcomingAppointments': upcoming,
            'upcoming_appointments': upcoming,
        }, status=status.HTTP_200_OK)


class DoctorPatientListView(views.APIView):
    """
    Roster of unique patients who have booked or completed consultations with the authenticated doctor.
    Enforces strict doctor isolation and clinical privacy boundaries.
    """
    permission_classes = [IsAuthenticated, IsDoctor]

    def get(self, request):
        doctor = _get_authenticated_doctor(request)

        # Base query strictly scoped to this doctor's appointments
        appts_qs = Appointment.objects.filter(
            doctor=doctor
        ).select_related(
            'patient_profile__user',
            'dependent__profile__user'
        ).order_by('date', 'created_at')

        search = request.query_params.get('search', '').strip()
        if search:
            appts_qs = appts_qs.filter(
                Q(patient_name_snapshot__icontains=search) |
                Q(patient_phone_snapshot__icontains=search) |
                Q(patient_profile__user__name__icontains=search) |
                Q(patient_profile__user__phone__icontains=search) |
                Q(dependent__name__icontains=search)
            )

        # Group appointments by distinct patient identity (primary patient vs dependent)
        patient_map = {}
        for appt in appts_qs:
            if appt.dependent:
                key = ('dependent', appt.dependent_id)
                patient_id = str(appt.dependent.id)
                patient_name = appt.patient_name_snapshot or appt.dependent.name
                patient_phone = appt.patient_phone_snapshot or (
                    appt.dependent.profile.user.phone if hasattr(appt.dependent.profile, 'user') else ""
                )
                gender = appt.dependent.gender or ""
                blood_group = appt.dependent.blood_group or ""
            elif appt.patient_profile:
                key = ('primary', appt.patient_profile_id)
                patient_id = str(appt.patient_profile.id)
                patient_name = appt.patient_name_snapshot or (
                    appt.patient_profile.user.name if hasattr(appt.patient_profile, 'user') else ""
                )
                patient_phone = appt.patient_phone_snapshot or (
                    appt.patient_profile.user.phone if hasattr(appt.patient_profile, 'user') else ""
                )
                gender = appt.patient_profile.gender or ""
                blood_group = appt.patient_profile.blood_group or ""
            else:
                continue

            appt_date_str = str(appt.date)

            if key not in patient_map:
                patient_map[key] = {
                    'patientId': patient_id,
                    'patient_id': patient_id,
                    'patientName': patient_name,
                    'patient_name': patient_name,
                    'patientPhone': patient_phone,
                    'patient_phone': patient_phone,
                    'totalVisits': 1,
                    'total_visits': 1,
                    'firstVisitDate': appt_date_str,
                    'first_visit_date': appt_date_str,
                    'lastVisitDate': appt_date_str,
                    'last_visit_date': appt_date_str,
                    'latestNotes': appt.notes or '',
                    'latest_notes': appt.notes or '',
                    'gender': gender,
                    'bloodGroup': blood_group,
                    'blood_group': blood_group,
                }
            else:
                entry = patient_map[key]
                entry['totalVisits'] += 1
                entry['total_visits'] += 1
                if appt_date_str < entry['firstVisitDate']:
                    entry['firstVisitDate'] = appt_date_str
                    entry['first_visit_date'] = appt_date_str
                if appt_date_str >= entry['lastVisitDate']:
                    entry['lastVisitDate'] = appt_date_str
                    entry['last_visit_date'] = appt_date_str
                    # latestNotes comes strictly from this doctor's latest appointment
                    entry['latestNotes'] = appt.notes or ''
                    entry['latest_notes'] = appt.notes or ''

        patient_list = list(patient_map.values())
        # Sort by most recent visit descending
        patient_list.sort(key=lambda p: p['lastVisitDate'], reverse=True)

        # Pagination
        total_count = len(patient_list)
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        try:
            page_size = min(50, max(1, int(request.query_params.get('page_size', 10))))
        except (ValueError, TypeError):
            page_size = 10

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = patient_list[start_idx:end_idx]

        return Response({
            'count': total_count,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'results': paginated_items,
        }, status=status.HTTP_200_OK)
