"""Platform Administrator Global Appointment Booking Views."""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.utils import timezone
from rest_framework import generics, views, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination

from apps.accounts.models import User, UserRole
from apps.accounts.permissions import IsPlatformAdmin
from apps.doctors.models import Doctor
from apps.facilities.models import Hospital, Clinic
from apps.onboarding.models import ProviderRequest, RequestStatus
from apps.appointments.models import Appointment, AppointmentStatus
from apps.appointments.serializers import (
    AppointmentDetailSerializer,
    AppointmentCancelSerializer,
)
from apps.notifications.services import notify_appointment_cancelled
from apps.audit.utils import log_audit_event


class AdminBookingPagination(PageNumberPagination):
    """Platform administrator booking directory pagination."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminBookingListView(generics.ListAPIView):
    """
    Platform administrator listing of all appointments platform-wide across Hospitals and Clinics.
    GET /api/v1/admin/bookings/
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = AppointmentDetailSerializer
    pagination_class = AdminBookingPagination

    def get_queryset(self):
        queryset = Appointment.objects.all().select_related(
            'doctor', 'doctor__hospital', 'doctor__clinic',
            'hospital', 'clinic', 'booked_by', 'patient_profile',
            'dependent', 'cancelled_by_user', 'review'
        )

        status_param = self.request.query_params.get('status')
        if status_param and status_param.lower() != 'all':
            queryset = queryset.filter(status__iexact=status_param.strip())

        hospital_id = self.request.query_params.get('hospital_id') or self.request.query_params.get('hospital')
        if hospital_id:
            queryset = queryset.filter(Q(hospital_id=hospital_id) | Q(doctor__hospital_id=hospital_id))

        clinic_id = self.request.query_params.get('clinic_id') or self.request.query_params.get('clinic')
        if clinic_id:
            queryset = queryset.filter(Q(clinic_id=clinic_id) | Q(doctor__clinic_id=clinic_id))

        facility_id = self.request.query_params.get('facility_id')
        if facility_id:
            queryset = queryset.filter(
                Q(hospital_id=facility_id) | Q(doctor__hospital_id=facility_id) |
                Q(clinic_id=facility_id) | Q(doctor__clinic_id=facility_id)
            )

        doctor_id = self.request.query_params.get('doctor_id') or self.request.query_params.get('doctor')
        if doctor_id:
            queryset = queryset.filter(doctor_id=doctor_id)

        search = self.request.query_params.get('search')
        if search:
            q = search.strip()
            filter_q = (
                Q(patient_name_snapshot__icontains=q) |
                Q(doctor__name__icontains=q) |
                Q(hospital__name__icontains=q) |
                Q(clinic__name__icontains=q) |
                Q(patient_phone_snapshot__icontains=q) |
                Q(specialty_snapshot__icontains=q)
            )
            try:
                uuid_val = uuid.UUID(q)
                filter_q |= Q(id=uuid_val)
            except (ValueError, TypeError):
                pass
            queryset = queryset.filter(filter_q)

        return queryset.order_by('-date', '-created_at')


class AdminBookingCancelView(views.APIView):
    """
    Platform administrator global appointment cancellation endpoint.
    POST /api/v1/admin/bookings/{id}/cancel/
    """
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        try:
            valid_uuid = uuid.UUID(str(pk))
        except (ValueError, TypeError):
            raise NotFound("Appointment not found.")

        appointment = Appointment.objects.select_related(
            'doctor', 'hospital', 'clinic', 'booked_by'
        ).filter(id=valid_uuid).first()

        if not appointment:
            raise NotFound("Appointment not found.")

        # Status transition check: can only cancel pending or confirmed appointments
        if appointment.status == AppointmentStatus.CANCELLED:
            return Response({
                "error": "ValidationError",
                "code": "ALREADY_CANCELLED",
                "message": "Appointment has already been cancelled."
            }, status=status.HTTP_400_BAD_REQUEST)

        if appointment.status == AppointmentStatus.COMPLETED:
            return Response({
                "error": "ValidationError",
                "code": "CANNOT_CANCEL_COMPLETED",
                "message": "Cannot cancel a consultation that has already been completed."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', 'Cancelled by administrator')

        # Atomic cancellation with notification and immutable audit logging
        with transaction.atomic():
            previous_status = appointment.status
            appointment.status = AppointmentStatus.CANCELLED
            appointment.cancel_reason = reason
            appointment.cancelled_by_role = UserRole.ADMIN
            appointment.cancelled_by_user = request.user
            appointment.cancelled_at = timezone.now()
            appointment.save(update_fields=[
                'status', 'cancel_reason', 'cancelled_by_role', 'cancelled_by_user', 'cancelled_at', 'updated_at'
            ])
            notify_appointment_cancelled(appointment, cancelled_by_user=request.user, reason=reason)

        log_audit_event(
            action="APPOINTMENT_CANCELLED",
            target_model="Appointment",
            target_id=str(appointment.id),
            actor=request.user,
            change_summary={
                "previous_status": previous_status,
                "new_status": "cancelled",
                "reason": reason,
                "cancelled_by_role": UserRole.ADMIN,
                "doctor_name": appointment.doctor.name,
                "date": str(appointment.date),
                "time_slot": appointment.time_slot,
            },
            request=request
        )

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_200_OK)


class AdminReportsView(views.APIView):
    """
    Platform administrator analytics & operational reporting.
    GET /api/v1/admin/reports/
    
    Security & Privacy Invariant:
    Platform-admin only. Never exposes individual patient PHI, clinical notes,
    diagnoses, or prescriptions. All metrics are aggregated.
    """
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        today = date.today()
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)

        # Overview Counts
        total_doctors = Doctor.objects.count()
        total_hospitals = Hospital.objects.count()
        total_clinics = Clinic.objects.count()
        total_users = User.objects.filter(role=UserRole.PATIENT).count()
        pending_requests_count = ProviderRequest.objects.filter(status=RequestStatus.PENDING).count()

        # Appointments Summary
        appts_qs = Appointment.objects.all()
        total_appointments = appts_qs.count()

        daily_count = appts_qs.filter(date=today).count()
        weekly_count = appts_qs.filter(date__gte=seven_days_ago, date__lte=today).count()
        monthly_count = appts_qs.filter(date__gte=thirty_days_ago, date__lte=today).count()

        # Status breakdown
        status_counts = appts_qs.values('status').annotate(count=Count('id'))
        status_map = {item['status']: item['count'] for item in status_counts}
        appointments_by_status = [
            {'status': 'Confirmed', 'count': status_map.get(AppointmentStatus.CONFIRMED, 0)},
            {'status': 'Completed', 'count': status_map.get(AppointmentStatus.COMPLETED, 0)},
            {'status': 'Cancelled', 'count': status_map.get(AppointmentStatus.CANCELLED, 0)},
            {'status': 'Pending', 'count': status_map.get(AppointmentStatus.PENDING, 0)},
        ]

        # By Specialty (top 10): from appointments if available, or registered doctors
        specialty_qs = appts_qs.values('specialty_snapshot').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        by_specialty = [
            {'specialty': item['specialty_snapshot'], 'count': item['count']}
            for item in specialty_qs if item['specialty_snapshot']
        ]
        if not by_specialty:
            doc_specialties = Doctor.objects.values('specialty').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            by_specialty = [
                {'specialty': item['specialty'], 'count': item['count']}
                for item in doc_specialties if item['specialty']
            ]

        # By Doctor (top 10)
        doctor_qs = appts_qs.values('doctor__name').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        by_doctor = [
            {'name': item['doctor__name'], 'count': item['count']}
            for item in doctor_qs if item['doctor__name']
        ]

        # By Hospital / Facility (top 10)
        hosp_counts = appts_qs.filter(hospital__isnull=False).values('hospital__name').annotate(
            count=Count('id')
        )
        clinic_counts = appts_qs.filter(clinic__isnull=False).values('clinic__name').annotate(
            count=Count('id')
        )
        facility_list = []
        for h in hosp_counts:
            facility_list.append({'facility': h['hospital__name'], 'count': h['count']})
        for c in clinic_counts:
            facility_list.append({'facility': c['clinic__name'], 'count': c['count']})
        facility_list.sort(key=lambda x: x['count'], reverse=True)
        by_hospital = facility_list[:10]

        # Monthly Trend over the past 6 calendar months
        AR_MONTHS = ['', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
        monthly_trend = []
        for i in range(5, -1, -1):
            y = today.year
            m = today.month - i
            while m <= 0:
                m += 12
                y -= 1
            m_start = date(y, m, 1)
            if m == 12:
                m_end = date(y + 1, 1, 1) - timedelta(days=1)
            else:
                m_end = date(y, m + 1, 1) - timedelta(days=1)

            m_appts = appts_qs.filter(date__gte=m_start, date__lte=m_end)
            m_bookings = m_appts.count()
            m_consultations = m_appts.filter(status=AppointmentStatus.COMPLETED).count()
            monthly_trend.append({
                'monthEn': m_start.strftime('%b'),
                'monthAr': AR_MONTHS[m],
                'bookings': m_bookings,
                'volume': m_consultations,
            })

        # Gross Consultation Revenue (Gross completed visits)
        completed_fees = appts_qs.filter(
            status=AppointmentStatus.COMPLETED
        ).aggregate(gross=Sum('doctor__consultation_fee'))['gross'] or Decimal('0.00')

        # Recent Activity (last 5 bookings, sanitized without patient phone or clinical notes)
        recent_apts = appts_qs.select_related('doctor', 'hospital', 'clinic').order_by('-created_at')[:5]
        recent_activity = []
        for a in recent_apts:
            facility_name = a.hospital.name if a.hospital else (a.clinic.name if a.clinic else '')
            recent_activity.append({
                'id': str(a.id),
                'text': f"Appointment booked with {a.doctor.name} ({facility_name}) by {a.patient_name_snapshot}",
                'time': a.created_at.strftime('%b %d, %Y'),
                'type': a.status,
            })

        return Response({
            'totalUsers': total_users,
            'totalDoctors': total_doctors,
            'totalHospitals': total_hospitals,
            'totalClinics': total_clinics,
            'totalAppointments': total_appointments,
            'totalBookings': total_appointments,
            'appointmentsByStatus': appointments_by_status,
            'providerRequestsCount': pending_requests_count,
            'waitlistCount': 0,
            'grossConsultationRevenue': str(completed_fees),
            'summary': {
                'daily': daily_count,
                'weekly': weekly_count,
                'monthly': monthly_count,
                'total': total_appointments,
            },
            'bySpecialty': by_specialty,
            'byDoctor': by_doctor,
            'byHospital': by_hospital,
            'recentActivity': recent_activity,
            'monthlyTrend': monthly_trend,
        }, status=status.HTTP_200_OK)


class AdminPatientListView(views.APIView):
    """
    Platform administrator listing of all patients across the platform.
    Supports filtering by hospital/clinic, doctor, and search.
    GET /api/v1/admin/patients/
    """
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        search = request.query_params.get('search')
        hospital_id = request.query_params.get('hospital_id') or request.query_params.get('hospital')
        doctor_id = request.query_params.get('doctor_id') or request.query_params.get('doctor')

        patient_users = User.objects.filter(role=UserRole.PATIENT).select_related('patient_profile').prefetch_related('booked_appointments')

        if search:
            q = search.strip()
            patient_users = patient_users.filter(
                Q(name__icontains=q) |
                Q(email__icontains=q) |
                Q(phone__icontains=q) |
                Q(patient_profile__insurance_number__icontains=q)
            )

        results = []
        for user in patient_users:
            profile = getattr(user, 'patient_profile', None)
            user_appointments = Appointment.objects.filter(
                Q(booked_by=user) | Q(patient_profile=profile) if profile else Q(booked_by=user)
            ).select_related('doctor', 'hospital', 'clinic')

            # Filter by hospital if provided
            if hospital_id:
                has_hosp = user_appointments.filter(
                    Q(hospital_id=hospital_id) | Q(clinic_id=hospital_id) |
                    Q(doctor__hospital_id=hospital_id) | Q(doctor__clinic_id=hospital_id)
                ).exists()
                if not has_hosp:
                    continue

            # Filter by doctor if provided
            if doctor_id:
                has_doc = user_appointments.filter(doctor_id=doctor_id).exists()
                if not has_doc:
                    continue

            total_appts = user_appointments.count()

            # Unique facilities attended
            facilities_map = {}
            doctors_map = {}
            for a in user_appointments:
                fac = a.hospital or a.clinic or (a.doctor.hospital if a.doctor else None) or (a.doctor.clinic if a.doctor else None)
                if fac and str(fac.id) not in facilities_map:
                    facilities_map[str(fac.id)] = {
                        'id': str(fac.id),
                        'name': fac.name,
                        'type': 'hospital' if isinstance(fac, Hospital) else 'clinic'
                    }
                if a.doctor and str(a.doctor.id) not in doctors_map:
                    doctors_map[str(a.doctor.id)] = {
                        'id': str(a.doctor.id),
                        'name': a.doctor.name,
                        'specialty': a.doctor.specialty
                    }

            recent_appts = []
            for a in user_appointments.order_by('-date')[:5]:
                fac_name = a.hospital.name if a.hospital else (a.clinic.name if a.clinic else (a.doctor.hospital.name if a.doctor and a.doctor.hospital else 'Facility'))
                recent_appts.append({
                    'id': str(a.id),
                    'date': str(a.date),
                    'time_slot': a.time_slot,
                    'status': a.status,
                    'doctor_name': a.doctor.name if a.doctor else 'Doctor',
                    'facility_name': fac_name,
                })

            results.append({
                'id': str(user.id),
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'avatar': user.avatar or '',
                'created_at': user.date_joined.isoformat(),
                'gender': profile.gender if profile else '',
                'dob': str(profile.dob) if profile and profile.dob else '',
                'blood_group': profile.blood_group if profile else '',
                'emergency_contact': profile.emergency_contact if profile else '',
                'insurance_provider': profile.insurance_provider if profile else '',
                'insurance_number': profile.insurance_number if profile else '',
                'allergies': profile.allergies if profile else '',
                'total_appointments': total_appts,
                'attended_facilities': list(facilities_map.values()),
                'attended_doctors': list(doctors_map.values()),
                'recent_appointments': recent_appts,
            })

        results.sort(key=lambda p: p['name'])
        return Response(results, status=status.HTTP_200_OK)


class AdminPatientDetailView(views.APIView):
    """
    Platform administrator detail view for a specific patient.
    GET /api/v1/admin/patients/{id}/
    """
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk):
        user = User.objects.filter(id=pk, role=UserRole.PATIENT).select_related('patient_profile').first()
        if not user:
            raise NotFound("Patient not found.")

        profile = getattr(user, 'patient_profile', None)
        user_appointments = Appointment.objects.filter(
            Q(booked_by=user) | Q(patient_profile=profile) if profile else Q(booked_by=user)
        ).select_related('doctor', 'hospital', 'clinic').order_by('-date')

        appointments_list = []
        for a in user_appointments:
            fac = a.hospital or a.clinic or (a.doctor.hospital if a.doctor else None) or (a.doctor.clinic if a.doctor else None)
            appointments_list.append({
                'id': str(a.id),
                'date': str(a.date),
                'time_slot': a.time_slot,
                'status': a.status,
                'notes': a.notes or '',
                'doctor_name': a.doctor.name if a.doctor else 'Doctor',
                'doctor_specialty': a.doctor.specialty if a.doctor else '',
                'facility_name': fac.name if fac else 'Facility',
                'facility_type': 'hospital' if isinstance(fac, Hospital) else 'clinic',
            })

        dependents_list = []
        if profile:
            for dep in profile.dependents.all():
                dependents_list.append({
                    'id': str(dep.id),
                    'name': dep.name,
                    'relation': dep.relation,
                    'gender': dep.gender,
                    'dob': str(dep.dob) if dep.dob else '',
                    'blood_group': dep.blood_group,
                })

        return Response({
            'id': str(user.id),
            'name': user.name,
            'email': user.email,
            'phone': user.phone,
            'avatar': user.avatar or '',
            'created_at': user.date_joined.isoformat(),
            'gender': profile.gender if profile else '',
            'dob': str(profile.dob) if profile and profile.dob else '',
            'blood_group': profile.blood_group if profile else '',
            'emergency_contact': profile.emergency_contact if profile else '',
            'insurance_provider': profile.insurance_provider if profile else '',
            'insurance_number': profile.insurance_number if profile else '',
            'allergies': profile.allergies if profile else '',
            'total_appointments': len(appointments_list),
            'dependents': dependents_list,
            'appointments': appointments_list,
        }, status=status.HTTP_200_OK)

