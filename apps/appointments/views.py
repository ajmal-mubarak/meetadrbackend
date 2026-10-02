"""Appointment Booking, Lifecycle, and Management Views."""
from datetime import datetime, date
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.db.models import Q
from rest_framework import views, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import UserRole, PatientProfile, PatientDependent
from apps.accounts.permissions import IsPatient, IsDoctor, IsFacilityAdmin, IsPlatformAdmin
from apps.facilities.models import FacilityStatus
from apps.doctors.models import Doctor
from apps.appointments.models import Appointment, AppointmentStatus, DoctorReview, FacilityReview
from apps.appointments.serializers import (
    AppointmentCreateSerializer,
    AppointmentCancelSerializer,
    AppointmentStatusUpdateSerializer,
    AppointmentDetailSerializer,
    DoctorReviewCreateSerializer,
    DoctorReviewDetailSerializer,
    FacilityReviewCreateSerializer,
    FacilityReviewDetailSerializer
)
from apps.appointments.services import recalculate_doctor_rating
from apps.audit.utils import log_audit_event
from apps.notifications.services import (
    notify_appointment_booked,
    notify_appointment_confirmed,
    notify_appointment_cancelled,
    notify_appointment_completed,
    notify_review_submitted,
)

def is_slot_already_booked_error(exc: IntegrityError) -> bool:
    """
    Detect if an IntegrityError was caused strictly by the unique_active_doctor_slot constraint.
    Re-raises any unrelated IntegrityErrors (check constraints, foreign keys, not-null constraints,
    or other unique constraints).
    """
    cause = getattr(exc, '__cause__', None)
    if cause:
        diag = getattr(cause, 'diag', None)
        if diag:
            constraint_name = getattr(diag, 'constraint_name', None)
            if constraint_name:
                return constraint_name == 'unique_active_doctor_slot'

    err_str = str(exc).lower()
    # Direct match on the specific constraint name (PostgreSQL / SQLite named constraint)
    if 'unique_active_doctor_slot' in err_str:
        return True

    # For SQLite, which outputs:
    # "UNIQUE constraint failed: meetadr_appointments.doctor_id, meetadr_appointments.date, meetadr_appointments.time_slot"
    # Ensure it is strictly on meetadr_appointments and contains all 3 composite columns:
    if 'meetadr_appointments' in err_str and 'unique' in err_str:
        required_fields = ['doctor_id', 'date', 'time_slot']
        if all(field in err_str for field in required_fields):
            return True

    return False

class AppointmentBookingView(views.APIView):
    """
    Authenticated patient consultation booking endpoint.
    Atomic concurrency-safe slot allocation preventing double-booking.
    """
    permission_classes = [IsPatient]

    def post(self, request):
        serializer = AppointmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        doctor_id = data['doctor_id']
        target_date = data['date']
        time_slot = data['time_slot'].strip()
        dependent_id = data.get('dependent_id')
        notes = data.get('notes', '')
        input_phone = data.get('patient_phone', '').strip()

        # 1. Validate Doctor & Facility Active Status
        doctor = Doctor.objects.select_related('hospital', 'clinic', 'schedule').filter(
            id=doctor_id,
            status=FacilityStatus.ACTIVE
        ).first()

        if not doctor:
            raise NotFound("Doctor not found or not active.")

        facility = doctor.hospital or doctor.clinic
        if not facility or facility.status != FacilityStatus.ACTIVE:
            return Response({
                "error": "ValidationError",
                "code": "INACTIVE_FACILITY",
                "message": "Doctor's affiliated medical facility is not active."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Date and Schedule Verification
        if target_date < date.today():
            return Response({
                "error": "ValidationError",
                "code": "INVALID_DATE",
                "message": "Cannot schedule appointments for past dates."
            }, status=status.HTTP_400_BAD_REQUEST)

        day_name = target_date.strftime('%A')
        schedule = getattr(doctor, 'schedule', None)
        if not schedule or day_name not in schedule.available_days:
            return Response({
                "error": "ValidationError",
                "code": "DOCTOR_UNAVAILABLE",
                "message": f"Dr. {doctor.name} is not available on {day_name}s."
            }, status=status.HTTP_400_BAD_REQUEST)

        standard_slots = schedule.standard_slots or []
        if time_slot not in standard_slots:
            def _normalize_time(t_str):
                import re
                start = t_str.split('-')[0].strip()
                m = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)?$', start, re.IGNORECASE)
                if not m:
                    return None
                hr, mn, mer = int(m.group(1)), int(m.group(2)), (m.group(3) or '').upper()
                if mer == 'PM' and hr < 12: hr += 12
                if mer == 'AM' and hr == 12: hr = 0
                return (hr, mn)

            norm_input = _normalize_time(time_slot)
            matched_slot = None
            if norm_input:
                for s in standard_slots:
                    if _normalize_time(s) == norm_input:
                        matched_slot = s
                        break
            if matched_slot:
                time_slot = matched_slot
            else:
                return Response({
                    "error": "ValidationError",
                    "code": "INVALID_SLOT",
                    "message": f"'{time_slot}' is not a valid consultation time slot for this doctor."
                }, status=status.HTTP_400_BAD_REQUEST)

        # 3. Patient Identity Resolution (Self vs Dependent)
        profile, _ = PatientProfile.objects.get_or_create(user=request.user)

        if dependent_id:
            dependent = PatientDependent.objects.filter(
                id=dependent_id,
                profile=profile
            ).first()
            if not dependent:
                return Response({
                    "error": "ValidationError",
                    "code": "DEPENDENT_NOT_FOUND",
                    "message": "The specified dependent does not exist or does not belong to your account."
                }, status=status.HTTP_404_NOT_FOUND)

            patient_profile = None
            patient_name_snapshot = dependent.name
            patient_phone_snapshot = input_phone or dependent.emergency_contact or getattr(profile, 'phone', '')
            patient_email_snapshot = request.user.email
        else:
            dependent = None
            patient_profile = profile
            patient_name_snapshot = request.user.name
            patient_phone_snapshot = input_phone or getattr(profile, 'phone', '') or getattr(request.user, 'phone', '') or ''
            patient_email_snapshot = request.user.email

        # 4. Preliminary Availability Pre-Check
        is_already_booked = Appointment.objects.filter(
            doctor=doctor,
            date=target_date,
            time_slot=time_slot,
            status__in=[AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING]
        ).exists()

        if is_already_booked:
            return Response({
                "error": "ConflictError",
                "code": "SLOT_ALREADY_BOOKED",
                "message": f"The selected time slot ({time_slot}) with Dr. {doctor.name} has already been booked.",
                "details": {}
            }, status=status.HTTP_409_CONFLICT)

        # 5. Authoritative Concurrency-Safe Database Insertion
        try:
            with transaction.atomic():
                appointment = Appointment.objects.create(
                    booked_by=request.user,
                    patient_profile=patient_profile,
                    dependent=dependent,
                    doctor=doctor,
                    hospital=doctor.hospital,
                    clinic=doctor.clinic,
                    patient_name_snapshot=patient_name_snapshot,
                    patient_phone_snapshot=patient_phone_snapshot,
                    patient_email_snapshot=patient_email_snapshot,
                    specialty_snapshot=doctor.specialty,
                    date=target_date,
                    time_slot=time_slot,
                    status=AppointmentStatus.CONFIRMED,
                    notes=notes
                )
                notify_appointment_booked(appointment)
        except IntegrityError as exc:
            if is_slot_already_booked_error(exc):
                return Response({
                    "error": "ConflictError",
                    "code": "SLOT_ALREADY_BOOKED",
                    "message": f"The selected time slot ({time_slot}) with Dr. {doctor.name} has already been booked.",
                    "details": {}
                }, status=status.HTTP_409_CONFLICT)
            raise

        # 6. Immutable Audit Log Creation
        log_audit_event(
            action="APPOINTMENT_CREATED",
            target_model="Appointment",
            target_id=str(appointment.id),
            actor=request.user,
            change_summary={
                "doctor_id": str(doctor.id),
                "doctor_name": doctor.name,
                "date": str(target_date),
                "time_slot": time_slot,
                "status": appointment.status,
                "for_dependent": bool(dependent),
                "patient_name": patient_name_snapshot
            },
            request=request
        )

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_201_CREATED)

class PatientAppointmentListView(generics.ListAPIView):
    """List appointments booked by the authenticated patient."""
    permission_classes = [IsPatient]
    serializer_class = AppointmentDetailSerializer

    def get_queryset(self):
        queryset = Appointment.objects.filter(
            booked_by=self.request.user
        ).select_related(
            'doctor', 'hospital', 'clinic', 'patient_profile', 'dependent', 'cancelled_by_user', 'review'
        ).order_by('-date', '-created_at')

        status_param = self.request.query_params.get('status')
        if status_param and status_param.lower() != 'all':
            queryset = queryset.filter(status=status_param.lower().strip())

        return queryset

class AppointmentDetailView(views.APIView):
    """Retrieve details of a single appointment with object-level security."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        appointment = Appointment.objects.select_related(
            'doctor', 'hospital', 'clinic', 'patient_profile', 'dependent', 'booked_by', 'cancelled_by_user', 'review'
        ).filter(id=pk).first()

        if not appointment:
            raise NotFound("Appointment not found.")

        user = request.user
        is_authorized = False

        if user.role == UserRole.PATIENT:
            is_authorized = (appointment.booked_by_id == user.id)
        elif user.role == UserRole.DOCTOR:
            is_authorized = hasattr(user, 'doctor_profile') and (appointment.doctor_id == user.doctor_profile.id)
        elif user.role == UserRole.HOSPITAL:
            if hasattr(user, 'hospital_facility') and user.hospital_facility:
                is_authorized = (appointment.hospital_id == user.hospital_facility.id)
            elif hasattr(user, 'clinic_facility') and user.clinic_facility:
                is_authorized = (appointment.clinic_id == user.clinic_facility.id)
        elif user.role == UserRole.ADMIN or user.is_staff or user.is_superuser:
            is_authorized = True

        if not is_authorized:
            # Mask existence to prevent IDOR / enumeration
            raise NotFound("Appointment not found.")

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_200_OK)

class AppointmentCancelView(views.APIView):
    """
    Cancel an appointment.
    Authorized for owning Patient, attending Doctor, facility Administrator, or Platform Admin.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        appointment = Appointment.objects.select_related(
            'doctor', 'hospital', 'clinic', 'booked_by'
        ).filter(id=pk).first()

        if not appointment:
            raise NotFound("Appointment not found.")

        user = request.user
        role = user.role
        is_authorized = False

        if role == UserRole.PATIENT:
            is_authorized = (appointment.booked_by_id == user.id)
        elif role == UserRole.DOCTOR:
            is_authorized = hasattr(user, 'doctor_profile') and (appointment.doctor_id == user.doctor_profile.id)
        elif role == UserRole.HOSPITAL:
            if hasattr(user, 'hospital_facility') and user.hospital_facility:
                is_authorized = (appointment.hospital_id == user.hospital_facility.id)
            elif hasattr(user, 'clinic_facility') and user.clinic_facility:
                is_authorized = (appointment.clinic_id == user.clinic_facility.id)
        elif role == UserRole.ADMIN or user.is_staff or user.is_superuser:
            is_authorized = True

        if not is_authorized:
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

        if role == UserRole.PATIENT and appointment.status == AppointmentStatus.CONFIRMED:
            return Response({
                "error": "ValidationError",
                "code": "CANNOT_CANCEL_CONFIRMED",
                "message": "Confirmed consultations cannot be cancelled directly by patients. Please contact the medical facility or reschedule."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', 'Cancelled by user')

        # Execute cancellation atomically
        with transaction.atomic():
            previous_status = appointment.status
            appointment.status = AppointmentStatus.CANCELLED
            appointment.cancel_reason = reason
            appointment.cancelled_by_role = role
            appointment.cancelled_by_user = user
            appointment.cancelled_at = timezone.now()
            appointment.save(update_fields=[
                'status', 'cancel_reason', 'cancelled_by_role', 'cancelled_by_user', 'cancelled_at', 'updated_at'
            ])
            notify_appointment_cancelled(appointment, cancelled_by_user=user, reason=reason)

        # Audit event
        log_audit_event(
            action="APPOINTMENT_CANCELLED",
            target_model="Appointment",
            target_id=str(appointment.id),
            actor=user,
            change_summary={
                "previous_status": previous_status,
                "reason": reason,
                "cancelled_by_role": role
            },
            request=request
        )

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_200_OK)

class AppointmentRescheduleView(views.APIView):
    """
    Reschedule an existing appointment to a new date and time slot.
    Authorized for owning Patient, attending Doctor, facility Administrator, or Platform Admin.
    Updates the existing appointment in place without creating a duplicate record.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        appointment = Appointment.objects.select_related(
            'doctor', 'doctor__schedule', 'hospital', 'clinic', 'booked_by'
        ).filter(id=pk).first()

        if not appointment:
            raise NotFound("Appointment not found.")

        user = request.user
        role = user.role
        is_authorized = False

        if role == UserRole.PATIENT:
            is_authorized = (appointment.booked_by_id == user.id)
        elif role == UserRole.DOCTOR:
            is_authorized = hasattr(user, 'doctor_profile') and (appointment.doctor_id == user.doctor_profile.id)
        elif role == UserRole.HOSPITAL:
            if hasattr(user, 'hospital_facility') and user.hospital_facility:
                is_authorized = (appointment.hospital_id == user.hospital_facility.id)
            elif hasattr(user, 'clinic_facility') and user.clinic_facility:
                is_authorized = (appointment.clinic_id == user.clinic_facility.id)
        elif role == UserRole.ADMIN or user.is_staff or user.is_superuser:
            is_authorized = True

        if not is_authorized:
            raise NotFound("Appointment not found.")

        if appointment.status == AppointmentStatus.CANCELLED:
            return Response({
                "error": "ValidationError",
                "code": "CANNOT_RESCHEDULE_CANCELLED",
                "message": "Cannot reschedule an appointment that has been cancelled."
            }, status=status.HTTP_400_BAD_REQUEST)

        if appointment.status == AppointmentStatus.COMPLETED:
            return Response({
                "error": "ValidationError",
                "code": "CANNOT_RESCHEDULE_COMPLETED",
                "message": "Cannot reschedule an appointment that has already been completed."
            }, status=status.HTTP_400_BAD_REQUEST)

        date_val = request.data.get('date')
        slot_val = request.data.get('time_slot')

        if not date_val or not slot_val:
            return Response({
                "error": "ValidationError",
                "code": "MISSING_PARAMETERS",
                "message": "Both 'date' (YYYY-MM-DD) and 'time_slot' are required to reschedule."
            }, status=status.HTTP_400_BAD_REQUEST)

        from datetime import datetime, date as date_class
        try:
            if isinstance(date_val, str):
                target_date = datetime.strptime(date_val.strip(), '%Y-%m-%d').date()
            else:
                target_date = date_val
        except (ValueError, TypeError):
            return Response({
                "error": "ValidationError",
                "code": "INVALID_DATE_FORMAT",
                "message": "Invalid date format. Expected YYYY-MM-DD."
            }, status=status.HTTP_400_BAD_REQUEST)

        if target_date < date_class.today():
            return Response({
                "error": "ValidationError",
                "code": "INVALID_DATE",
                "message": "Cannot schedule appointments for past dates."
            }, status=status.HTTP_400_BAD_REQUEST)

        doctor = appointment.doctor
        day_name = target_date.strftime('%A')
        schedule = getattr(doctor, 'schedule', None)

        if not schedule or day_name not in schedule.available_days:
            return Response({
                "error": "ValidationError",
                "code": "DOCTOR_UNAVAILABLE",
                "message": f"Dr. {doctor.name} is not available on {day_name}s."
            }, status=status.HTTP_400_BAD_REQUEST)

        time_slot = str(slot_val).strip()
        standard_slots = schedule.standard_slots or []
        if time_slot not in standard_slots:
            def _normalize_time(t_str):
                import re
                start = t_str.split('-')[0].strip()
                m = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)?$', start, re.IGNORECASE)
                if not m:
                    return None
                hr, mn, mer = int(m.group(1)), int(m.group(2)), (m.group(3) or '').upper()
                if mer == 'PM' and hr < 12: hr += 12
                if mer == 'AM' and hr == 12: hr = 0
                return (hr, mn)

            norm_input = _normalize_time(time_slot)
            matched_slot = None
            if norm_input:
                for s in standard_slots:
                    if _normalize_time(s) == norm_input:
                        matched_slot = s
                        break
            if matched_slot:
                time_slot = matched_slot
            else:
                return Response({
                    "error": "ValidationError",
                    "code": "INVALID_SLOT",
                    "message": f"'{time_slot}' is not a valid consultation time slot for this doctor."
                }, status=status.HTTP_400_BAD_REQUEST)

        # Check collision with other active appointments (excluding this appointment itself)
        collision = Appointment.objects.filter(
            doctor=doctor,
            date=target_date,
            time_slot=time_slot
        ).exclude(id=appointment.id).exclude(status=AppointmentStatus.CANCELLED).exists()

        if collision:
            return Response({
                "error": "ConflictError",
                "code": "SLOT_ALREADY_BOOKED",
                "message": f"The selected time slot ({time_slot}) on {target_date} is already booked."
            }, status=status.HTTP_409_CONFLICT)

        old_date = appointment.date
        old_slot = appointment.time_slot

        with transaction.atomic():
            appointment.date = target_date
            appointment.time_slot = time_slot
            appointment.status = AppointmentStatus.CONFIRMED
            appointment.save(update_fields=['date', 'time_slot', 'status', 'updated_at'])

        # Audit event
        log_audit_event(
            action="APPOINTMENT_RESCHEDULED",
            target_model="Appointment",
            target_id=str(appointment.id),
            actor=user,
            change_summary={
                "previous_date": str(old_date),
                "new_date": str(target_date),
                "previous_slot": old_slot,
                "new_slot": time_slot,
            },
            request=request
        )

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_200_OK)

class DoctorAppointmentListView(generics.ListAPIView):
    """List appointments for the authenticated doctor with status, date, and search filters."""
    permission_classes = [IsDoctor]
    serializer_class = AppointmentDetailSerializer

    def get_queryset(self):
        doctor = self.request.user.doctor_profile
        queryset = Appointment.objects.filter(
            doctor=doctor
        ).select_related(
            'doctor', 'hospital', 'clinic', 'patient_profile', 'dependent', 'cancelled_by_user', 'review'
        ).order_by('-date', 'time_slot')

        status_param = self.request.query_params.get('status')
        if status_param and status_param.lower() != 'all':
            queryset = queryset.filter(status=status_param.lower().strip())

        date_param = self.request.query_params.get('date')
        if date_param:
            queryset = queryset.filter(date=date_param.strip())

        search_param = self.request.query_params.get('search')
        if search_param:
            search_param = search_param.strip()
            queryset = queryset.filter(
                Q(patient_name_snapshot__icontains=search_param) |
                Q(patient_phone_snapshot__icontains=search_param) |
                Q(patient_email_snapshot__icontains=search_param) |
                Q(specialty_snapshot__icontains=search_param) |
                Q(notes__icontains=search_param) |
                Q(id__icontains=search_param)
            )

        return queryset

class DoctorAppointmentStatusView(views.APIView):
    """Mark consultation completed, confirmed, or cancelled by attending doctor."""
    permission_classes = [IsDoctor]

    def patch(self, request, pk):
        doctor = request.user.doctor_profile
        appointment = Appointment.objects.filter(id=pk, doctor=doctor).first()
        if not appointment:
            raise NotFound("Appointment not found.")

        serializer = AppointmentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        # Enforce valid doctor transitions
        if new_status == AppointmentStatus.CONFIRMED:
            if appointment.status != AppointmentStatus.PENDING:
                return Response({
                    "error": "ValidationError",
                    "code": "INVALID_TRANSITION",
                    "message": f"Appointment is already '{appointment.status}'. Only pending appointments can be confirmed."
                }, status=status.HTTP_400_BAD_REQUEST)
        elif new_status == AppointmentStatus.COMPLETED:
            if appointment.status != AppointmentStatus.CONFIRMED:
                return Response({
                    "error": "ValidationError",
                    "code": "INVALID_TRANSITION",
                    "message": f"Cannot complete an appointment with status '{appointment.status}'. Must be 'confirmed'."
                }, status=status.HTTP_400_BAD_REQUEST)
        elif new_status == AppointmentStatus.CANCELLED:
            if appointment.status not in [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]:
                return Response({
                    "error": "ValidationError",
                    "code": "INVALID_TRANSITION",
                    "message": f"Cannot cancel an appointment with status '{appointment.status}'."
                }, status=status.HTTP_400_BAD_REQUEST)
            appointment.cancelled_by_role = UserRole.DOCTOR
            appointment.cancelled_by_user = request.user
            appointment.cancelled_at = timezone.now()
            appointment.cancel_reason = request.data.get('reason', 'Cancelled by doctor')

        with transaction.atomic():
            prev_status = appointment.status
            appointment.status = new_status
            appointment.save()
            if new_status == AppointmentStatus.CONFIRMED:
                notify_appointment_confirmed(appointment)
            elif new_status == AppointmentStatus.COMPLETED:
                notify_appointment_completed(appointment)
            elif new_status == AppointmentStatus.CANCELLED:
                notify_appointment_cancelled(appointment, cancelled_by_user=request.user, reason=appointment.cancel_reason)

        log_audit_event(
            action="APPOINTMENT_STATUS_UPDATED",
            target_model="Appointment",
            target_id=str(appointment.id),
            actor=request.user,
            change_summary={
                "previous_status": prev_status,
                "new_status": new_status,
                "updated_by": "doctor"
            },
            request=request
        )

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        """POST /api/v1/appointments/{id}/complete/ shortcut."""
        return self.patch(request, pk)

class HospitalAdminAppointmentListView(generics.ListAPIView):
    """List appointments for doctors belonging to the authenticated hospital or clinic."""
    permission_classes = [IsFacilityAdmin]
    serializer_class = AppointmentDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'hospital_facility') and user.hospital_facility:
            queryset = Appointment.objects.filter(hospital=user.hospital_facility)
        elif hasattr(user, 'clinic_facility') and user.clinic_facility:
            queryset = Appointment.objects.filter(clinic=user.clinic_facility)
        else:
            return Appointment.objects.none()

        queryset = queryset.select_related(
            'doctor', 'hospital', 'clinic', 'patient_profile', 'dependent', 'cancelled_by_user', 'review'
        ).order_by('date', 'time_slot')

        status_param = self.request.query_params.get('status')
        if status_param and status_param.lower() != 'all':
            queryset = queryset.filter(status=status_param.lower().strip())

        return queryset

class HospitalAdminAppointmentCancelView(views.APIView):
    """
    Facility administrator cancellation endpoint for doctors in their facility.
    POST /api/hospital-admin/appointments/{appointment_id}/cancel/
    """
    permission_classes = [IsFacilityAdmin]

    def post(self, request, pk):
        user = request.user
        facility = getattr(user, 'hospital_facility', None) or getattr(user, 'clinic_facility', None)
        if not facility:
            raise PermissionDenied("User is not associated with any active medical facility.")

        facility_filter = Q(hospital=user.hospital_facility) if hasattr(user, 'hospital_facility') and user.hospital_facility else Q(clinic=user.clinic_facility)

        # Strict facility isolation: ensure appointment belongs to this facility
        appointment = Appointment.objects.filter(
            Q(id=pk) & facility_filter
        ).first()

        if not appointment:
            raise NotFound("Appointment not found or does not belong to your facility.")

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
                "message": "Cannot cancel an already completed appointment."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', 'Cancelled by facility administrator')

        with transaction.atomic():
            prev_status = appointment.status
            appointment.status = AppointmentStatus.CANCELLED
            appointment.cancel_reason = reason
            appointment.cancelled_by_role = UserRole.HOSPITAL
            appointment.cancelled_by_user = user
            appointment.cancelled_at = timezone.now()
            appointment.save(update_fields=[
                'status', 'cancel_reason', 'cancelled_by_role', 'cancelled_by_user', 'cancelled_at', 'updated_at'
            ])
            notify_appointment_cancelled(appointment, cancelled_by_user=user, reason=reason)

        log_audit_event(
            action="FACILITY_ADMIN_APPOINTMENT_CANCELLED",
            target_model="Appointment",
            target_id=str(appointment.id),
            actor=user,
            change_summary={
                "previous_status": prev_status,
                "reason": reason,
                "facility_id": str(facility.id),
                "facility_name": facility.name
            },
            request=request
        )

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_200_OK)

class HospitalAdminAppointmentStatusView(views.APIView):
    """
    Facility administrator status updates (confirming or completing appointments).
    PATCH /api/v1/hospital/appointments/{id}/status/
    """
    permission_classes = [IsFacilityAdmin]

    def patch(self, request, pk):
        user = request.user
        facility = getattr(user, 'hospital_facility', None) or getattr(user, 'clinic_facility', None)
        if not facility:
            raise PermissionDenied("User is not associated with any medical facility.")

        facility_filter = Q(hospital=user.hospital_facility) if hasattr(user, 'hospital_facility') and user.hospital_facility else Q(clinic=user.clinic_facility)

        appointment = Appointment.objects.filter(
            Q(id=pk) & facility_filter
        ).first()

        if not appointment:
            raise NotFound("Appointment not found or does not belong to your facility.")

        serializer = AppointmentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        if new_status == AppointmentStatus.COMPLETED and appointment.status != AppointmentStatus.CONFIRMED:
            return Response({
                "error": "ValidationError",
                "code": "INVALID_TRANSITION",
                "message": f"Cannot complete an appointment with status '{appointment.status}'."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            prev_status = appointment.status
            appointment.status = new_status
            appointment.save(update_fields=['status', 'updated_at'])
            if new_status == AppointmentStatus.CONFIRMED:
                notify_appointment_confirmed(appointment)
            elif new_status == AppointmentStatus.COMPLETED:
                notify_appointment_completed(appointment)
            elif new_status == AppointmentStatus.CANCELLED:
                notify_appointment_cancelled(appointment, cancelled_by_user=user, reason=appointment.cancel_reason)

        log_audit_event(
            action="FACILITY_ADMIN_APPOINTMENT_STATUS_UPDATED",
            target_model="Appointment",
            target_id=str(appointment.id),
            actor=user,
            change_summary={
                "previous_status": prev_status,
                "new_status": new_status,
                "facility_name": facility.name
            },
            request=request
        )

        return Response(AppointmentDetailSerializer(appointment).data, status=status.HTTP_200_OK)

class AppointmentReviewView(views.APIView):
    """
    Post-consultation verified review endpoint.
    POST /api/v1/appointments/<uuid:pk>/review/ (Patient creates review)
    GET /api/v1/appointments/<uuid:pk>/review/ (Patient or attending Doctor reads review)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.data.get('review_type') == 'facility' or request.data.get('target') == 'facility':
            return AppointmentFacilityReviewView().post(request, pk)

        if request.user.role != UserRole.PATIENT:
            raise PermissionDenied("Only authenticated patients can submit reviews.")

        appointment = Appointment.objects.select_related('doctor', 'booked_by').filter(id=pk).first()
        if not appointment or appointment.booked_by_id != request.user.id:
            raise NotFound("Appointment not found.")

        if appointment.status != AppointmentStatus.COMPLETED:
            return Response({
                "error": "ValidationError",
                "code": "CANNOT_REVIEW_UNCOMPLETED",
                "message": "Only completed appointments can be reviewed."
            }, status=status.HTTP_400_BAD_REQUEST)

        if DoctorReview.objects.filter(appointment=appointment).exists():
            return Response({
                "error": "ConflictError",
                "code": "ALREADY_REVIEWED",
                "message": "This appointment has already been reviewed."
            }, status=status.HTTP_409_CONFLICT)

        serializer = DoctorReviewCreateSerializer(data=request.data)
        if not serializer.is_valid():
            if 'rating' in serializer.errors:
                return Response({
                    "error": "ValidationError",
                    "code": "INVALID_RATING",
                    "message": "Rating must be an integer between 1 and 5."
                }, status=status.HTTP_400_BAD_REQUEST)
            err_msg = serializer.errors.get('comment', ['Invalid input.'])[0] if 'comment' in serializer.errors else "Invalid input."
            return Response({
                "error": "ValidationError",
                "code": "INVALID_INPUT",
                "message": err_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                review = DoctorReview.objects.create(
                    appointment=appointment,
                    doctor=appointment.doctor,
                    patient=request.user,
                    rating=serializer.validated_data['rating'],
                    comment=serializer.validated_data.get('comment', ''),
                )
                recalculate_doctor_rating(appointment.doctor_id)
                notify_review_submitted(review)

                log_audit_event(
                    action="PATIENT_REVIEW_SUBMITTED",
                    target_model="DoctorReview",
                    target_id=str(review.id),
                    actor=request.user,
                    change_summary={
                        "doctor_id": str(appointment.doctor_id),
                        "appointment_id": str(appointment.id),
                        "rating": review.rating,
                        "review_id": str(review.id),
                    },
                    request=request
                )
        except IntegrityError:
            return Response({
                "error": "ConflictError",
                "code": "ALREADY_REVIEWED",
                "message": "This appointment has already been reviewed."
            }, status=status.HTTP_409_CONFLICT)

        return Response(DoctorReviewDetailSerializer(review).data, status=status.HTTP_201_CREATED)

    def get(self, request, pk):
        appointment = Appointment.objects.select_related(
            'doctor', 'doctor__user', 'booked_by'
        ).filter(id=pk).first()

        if not appointment:
            raise NotFound("Appointment not found.")

        user = request.user
        is_authorized = False

        if user.role == UserRole.PATIENT and appointment.booked_by_id == user.id:
            is_authorized = True
        elif user.role == UserRole.DOCTOR and hasattr(user, 'doctor_profile') and appointment.doctor_id == user.doctor_profile.id:
            is_authorized = True

        if not is_authorized:
            raise NotFound("Appointment not found.")

        review = DoctorReview.objects.select_related('doctor').filter(appointment=appointment).first()
        if not review:
            raise NotFound("No review found for this appointment.")

        return Response(DoctorReviewDetailSerializer(review).data, status=status.HTTP_200_OK)


class AppointmentFacilityReviewView(views.APIView):
    """
    Post-consultation verified facility (hospital or clinic) review endpoint.
    POST /api/v1/appointments/<uuid:pk>/facility-review/ (Patient creates review)
    GET /api/v1/appointments/<uuid:pk>/facility-review/ (Patient, Doctor, or Facility Admin reads review)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != UserRole.PATIENT:
            raise PermissionDenied("Only authenticated patients can submit reviews.")

        appointment = Appointment.objects.select_related('hospital', 'clinic', 'doctor', 'doctor__hospital', 'doctor__clinic', 'booked_by').filter(id=pk).first()
        if not appointment or appointment.booked_by_id != request.user.id:
            raise NotFound("Appointment not found.")

        if appointment.status != AppointmentStatus.COMPLETED:
            return Response({
                "error": "ValidationError",
                "code": "CANNOT_REVIEW_UNCOMPLETED",
                "message": "Only completed appointments can be reviewed."
            }, status=status.HTTP_400_BAD_REQUEST)

        if FacilityReview.objects.filter(appointment=appointment).exists():
            return Response({
                "error": "ConflictError",
                "code": "ALREADY_REVIEWED",
                "message": "This appointment facility has already been reviewed."
            }, status=status.HTTP_409_CONFLICT)

        hospital = appointment.hospital or (appointment.doctor.hospital if appointment.doctor else None)
        clinic = appointment.clinic or (appointment.doctor.clinic if appointment.doctor else None)

        if not hospital and not clinic:
            return Response({
                "error": "ValidationError",
                "code": "NO_FACILITY",
                "message": "No hospital or clinic is affiliated with this appointment."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = FacilityReviewCreateSerializer(data=request.data)
        if not serializer.is_valid():
            if 'rating' in serializer.errors:
                return Response({
                    "error": "ValidationError",
                    "code": "INVALID_RATING",
                    "message": "Rating must be an integer between 1 and 5."
                }, status=status.HTTP_400_BAD_REQUEST)
            err_msg = serializer.errors.get('comment', ['Invalid input.'])[0] if 'comment' in serializer.errors else "Invalid input."
            return Response({
                "error": "ValidationError",
                "code": "INVALID_INPUT",
                "message": err_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                review = FacilityReview.objects.create(
                    appointment=appointment,
                    hospital=hospital if hospital else None,
                    clinic=clinic if not hospital and clinic else None,
                    patient=request.user,
                    rating=serializer.validated_data['rating'],
                    comment=serializer.validated_data.get('comment', ''),
                )

                log_audit_event(
                    action="PATIENT_FACILITY_REVIEW_SUBMITTED",
                    target_model="FacilityReview",
                    target_id=str(review.id),
                    actor=request.user,
                    change_summary={
                        "hospital_id": str(hospital.id) if hospital else None,
                        "clinic_id": str(clinic.id) if clinic else None,
                        "appointment_id": str(appointment.id),
                        "rating": review.rating,
                        "review_id": str(review.id),
                    },
                    request=request
                )
        except IntegrityError:
            return Response({
                "error": "ConflictError",
                "code": "ALREADY_REVIEWED",
                "message": "This appointment facility has already been reviewed."
            }, status=status.HTTP_409_CONFLICT)

        return Response(FacilityReviewDetailSerializer(review).data, status=status.HTTP_201_CREATED)

    def get(self, request, pk):
        appointment = Appointment.objects.select_related(
            'hospital', 'clinic', 'booked_by'
        ).filter(id=pk).first()

        if not appointment:
            raise NotFound("Appointment not found.")

        user = request.user
        is_authorized = False

        if user.role == UserRole.PATIENT and appointment.booked_by_id == user.id:
            is_authorized = True
        elif user.role in [UserRole.HOSPITAL, UserRole.ADMIN, UserRole.DOCTOR]:
            is_authorized = True

        if not is_authorized:
            raise NotFound("Appointment not found.")

        review = FacilityReview.objects.select_related('hospital', 'clinic').filter(appointment=appointment).first()
        if not review:
            raise NotFound("No facility review found for this appointment.")

        return Response(FacilityReviewDetailSerializer(review).data, status=status.HTTP_200_OK)


