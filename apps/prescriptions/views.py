"""Prescription API Views for Issuance, Retrieval, and Lifecycle Management."""
from django.db import transaction, IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import UserRole
from apps.accounts.permissions import IsDoctor
from apps.appointments.models import Appointment, AppointmentStatus
from apps.audit.utils import log_audit_event
from apps.prescriptions.models import Prescription, PrescriptionMedication, PrescriptionStatus
from apps.prescriptions.serializers import (
    PrescriptionCreateSerializer,
    PrescriptionReadSerializer,
)
from apps.prescriptions.permissions import can_access_prescription
from apps.notifications.services import (
    notify_prescription_ready,
    notify_prescription_cancelled,
)


class PrescriptionCreateView(APIView):
    """
    POST /api/v1/prescriptions/
    
    Issues a structured digital prescription for a completed appointment.
    
    Security Invariants:
    - Only authenticated doctors with an active facility can issue prescriptions.
    - Doctor identity is strictly derived from request.user (never client payload).
    - Patient identity is strictly derived from appointment.booked_by.
    - Appointment must belong to the requesting doctor and be in COMPLETED status.
    - Appointment must not already have an ACTIVE prescription (returns 409).
    - Concurrency-safe: database partial UniqueConstraint enforces 1 active Rx per appointment.
    - Zero clinical PHI in audit logs.
    """
    permission_classes = [IsAuthenticated, IsDoctor]

    def post(self, request):
        serializer = PrescriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        doctor = request.user.doctor_profile

        # Verify doctor facility is active
        facility = doctor.hospital or doctor.clinic
        if not facility or getattr(facility, 'status', None) != 'Active':
            return Response(
                {"detail": "Prescriptions can only be issued by doctors affiliated with an active facility."},
                status=status.HTTP_403_FORBIDDEN
            )

        appointment_id = serializer.validated_data['appointment_id']

        # Look up appointment scoped to this doctor (return 404 if not found or different doctor)
        appointment = Appointment.objects.filter(id=appointment_id, doctor=doctor).first()
        if not appointment:
            return Response(
                {"detail": "Appointment not found or not assigned to you."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Invariant: Appointment must be completed
        if appointment.status != AppointmentStatus.COMPLETED:
            return Response(
                {"detail": "Prescriptions can only be issued for completed appointments."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check existing active prescription
        if appointment.prescriptions.filter(status=PrescriptionStatus.ACTIVE).exists():
            return Response(
                {"detail": "An active prescription already exists for this appointment."},
                status=status.HTTP_409_CONFLICT
            )

        # Atomically create Prescription and line items
        try:
            with transaction.atomic():
                prescription = Prescription.objects.create(
                    appointment=appointment,
                    doctor=doctor,
                    patient=appointment.booked_by,
                    diagnosis=serializer.validated_data['diagnosis'],
                    instructions=serializer.validated_data.get('instructions', ''),
                    status=PrescriptionStatus.ACTIVE,
                )
                medications_data = serializer.validated_data['medications']
                medication_objects = [
                    PrescriptionMedication(
                        prescription=prescription,
                        medication_name=med['medication_name'],
                        dosage=med['dosage'],
                        frequency=med['frequency'],
                        duration=med['duration'],
                        instructions=med.get('instructions', ''),
                    )
                    for med in medications_data
                ]
                PrescriptionMedication.objects.bulk_create(medication_objects)
                notify_prescription_ready(prescription)
        except IntegrityError:
            # Handles concurrent creation race condition caught by the partial unique constraint
            return Response(
                {"detail": "An active prescription already exists for this appointment."},
                status=status.HTTP_409_CONFLICT
            )

        # Audit event without clinical PHI
        log_audit_event(
            action='PRESCRIPTION_CREATED',
            target_model='Prescription',
            target_id=str(prescription.id),
            actor=request.user,
            change_summary={
                'appointment_id': str(appointment.id),
                'doctor_id': str(doctor.id),
                'patient_id': str(appointment.booked_by_id),
                'medication_count': len(medications_data),
                'status': prescription.status,
            },
            request=request
        )

        return Response(
            PrescriptionReadSerializer(prescription).data,
            status=status.HTTP_201_CREATED
        )


class PrescriptionMyListView(APIView):
    """
    GET /api/v1/prescriptions/my/
    
    Lists prescriptions for the authenticated caller:
    - Patients see prescriptions issued for their account (including dependents).
    - Doctors see prescriptions they have issued.
    - Other roles receive 403 Forbidden (preventing clinical PHI exposure).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == UserRole.PATIENT:
            prescriptions = Prescription.objects.filter(
                patient=user
            ).select_related(
                'appointment',
                'appointment__dependent',
                'doctor',
                'patient'
            ).prefetch_related('medications').order_by('-issued_at')
        elif user.role == UserRole.DOCTOR and hasattr(user, 'doctor_profile'):
            prescriptions = Prescription.objects.filter(
                doctor=user.doctor_profile
            ).select_related(
                'appointment',
                'appointment__dependent',
                'doctor',
                'patient'
            ).prefetch_related('medications').order_by('-issued_at')
        else:
            return Response(
                {"detail": "Access denied: Prescriptions are only accessible to patients and authorized clinicians."},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response(PrescriptionReadSerializer(prescriptions, many=True).data)


class PrescriptionDetailView(APIView):
    """
    GET /api/v1/prescriptions/{id}/
    
    Retrieves full details of a single prescription.
    
    Security Invariants:
    - Only owning patient, issuing doctor, or consulting doctor with active
      clinical relationship may access.
    - All other users receive 404 Not Found (fail closed, no disclosure).
    - Facility administrators and platform administrators receive 404.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        prescription = Prescription.objects.filter(
            id=pk
        ).select_related(
            'appointment',
            'appointment__dependent',
            'doctor',
            'patient'
        ).prefetch_related('medications').first()

        if not prescription:
            raise Http404("No prescription matches the given query.")

        # Object-level authorization check
        if not can_access_prescription(request.user, prescription):
            raise Http404("No prescription matches the given query.")

        return Response(PrescriptionReadSerializer(prescription).data)


class AppointmentPrescriptionView(APIView):
    """
    GET /api/v1/prescriptions/appointment/{appointment_id}/
    
    Retrieves the ACTIVE prescription for a specific appointment.
    
    Security Invariants:
    - Only the owning patient or attending doctor may query.
    - Historical cancelled prescriptions do not replace the active prescription.
    - If no active prescription exists, returns 404 Not Found.
    - Unrelated patients, unrelated doctors, and administrative roles receive 404.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, appointment_id):
        appointment = Appointment.objects.filter(id=appointment_id).first()
        if not appointment:
            raise Http404("No appointment matches the given query.")

        # Access check: Must be the patient who booked or the attending doctor
        is_patient = (appointment.booked_by_id == request.user.id)
        is_attending_doctor = (
            request.user.role == UserRole.DOCTOR and
            hasattr(request.user, 'doctor_profile') and
            appointment.doctor_id == request.user.doctor_profile.id
        )

        if not (is_patient or is_attending_doctor):
            raise Http404("No appointment matches the given query.")

        # Retrieve the ACTIVE prescription for this appointment
        active_prescription = appointment.prescriptions.filter(
            status=PrescriptionStatus.ACTIVE
        ).select_related(
            'appointment',
            'appointment__dependent',
            'doctor',
            'patient'
        ).prefetch_related('medications').first()

        if not active_prescription:
            return Response(
                {"detail": "No active prescription found for this appointment."},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(PrescriptionReadSerializer(active_prescription).data)


class PrescriptionCancelView(APIView):
    """
    POST /api/v1/prescriptions/{id}/cancel/
    
    Cancels an active prescription.
    
    Lifecycle Invariants:
    - Only the issuing doctor may cancel their prescription.
    - Unauthorized doctors or other roles receive 404 Not Found.
    - Record is NOT deleted and clinical data is NOT modified.
    - Once cancelled, a replacement prescription may be issued for the same appointment.
    - Audit event PRESCRIPTION_CANCELLED logged without clinical PHI.
    """
    permission_classes = [IsAuthenticated, IsDoctor]

    def post(self, request, pk):
        doctor = request.user.doctor_profile
        prescription = Prescription.objects.filter(id=pk, doctor=doctor).first()

        if not prescription:
            raise Http404("No prescription matches the given query.")

        if prescription.status == PrescriptionStatus.CANCELLED:
            return Response(
                {"detail": "Prescription is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            prescription.status = PrescriptionStatus.CANCELLED
            prescription.save(update_fields=['status'])
            notify_prescription_cancelled(prescription)

        # Audit event without clinical PHI
        log_audit_event(
            action='PRESCRIPTION_CANCELLED',
            target_model='Prescription',
            target_id=str(prescription.id),
            actor=request.user,
            change_summary={
                'appointment_id': str(prescription.appointment_id),
                'doctor_id': str(doctor.id),
                'patient_id': str(prescription.patient_id),
                'status': PrescriptionStatus.CANCELLED,
            },
            request=request
        )

        return Response(
            PrescriptionReadSerializer(prescription).data,
            status=status.HTTP_200_OK
        )
