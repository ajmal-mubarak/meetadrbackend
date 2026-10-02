"""Views for facility-scoped doctor roster management and IDOR protection."""
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from rest_framework import generics, views, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.permissions import IsFacilityAdmin
from apps.doctors.models import Doctor, DoctorSchedule
from apps.facilities.models import FacilityStatus
from apps.facilities.facility_views import get_facility_for_user
from apps.doctors.facility_serializers import (
    FacilityDoctorSerializer,
    FacilityDoctorStatusSerializer
)
from apps.audit.utils import log_audit_event

class FacilityDoctorListCreateView(generics.ListCreateAPIView):
    """
    Facility administrator doctor listing and onboarding endpoint.
    GET /api/v1/facility/doctors/
    POST /api/v1/facility/doctors/
    
    Security & Isolation Rules:
    - Scoped strictly to doctors belonging to the authenticated administrator's facility.
    - Creating a doctor derives the facility server-side from request.user.
    - Client-supplied facility IDs in POST body are strictly stripped/ignored.
    """
    permission_classes = [IsFacilityAdmin]
    serializer_class = FacilityDoctorSerializer

    def get_facility(self):
        fac_type, facility = get_facility_for_user(self.request.user)
        if not facility:
            raise PermissionDenied("User is not associated with an authorized medical facility.")
        return fac_type, facility

    def get_queryset(self):
        fac_type, facility = self.get_facility()

        if fac_type == 'hospital':
            queryset = Doctor.objects.filter(hospital=facility)
        else:
            queryset = Doctor.objects.filter(clinic=facility)

        queryset = queryset.select_related('hospital', 'clinic', 'schedule')

        status_param = self.request.query_params.get('status')
        if status_param and status_param.lower() != 'all':
            queryset = queryset.filter(status__iexact=status_param.strip())

        specialty = self.request.query_params.get('specialty')
        if specialty and specialty.lower() != 'all':
            queryset = queryset.filter(specialty__iexact=specialty.strip())

        search = self.request.query_params.get('search')
        if search:
            q = search.strip()
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(name_ar__icontains=q) |
                Q(specialty__icontains=q) |
                Q(education__icontains=q)
            )

        return queryset.order_by('name')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        fac_type, facility = get_facility_for_user(self.request.user)
        context['facility_type'] = fac_type
        context['facility'] = facility
        return context

    def perform_create(self, serializer):
        fac_type, facility = self.get_facility()
        doctor = serializer.save()

        log_audit_event(
            action="DOCTOR_CREATED",
            target_model="Doctor",
            target_id=str(doctor.id),
            actor=self.request.user,
            change_summary={
                "name": doctor.name,
                "specialty": doctor.specialty,
                "facility_id": str(facility.id),
                "facility_type": fac_type,
            },
            request=self.request
        )

class FacilityDoctorDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Facility-scoped doctor inspection, updating, and de-registration.
    GET /api/v1/facility/doctors/{id}/
    PATCH /api/v1/facility/doctors/{id}/
    DELETE /api/v1/facility/doctors/{id}/
    
    Cross-Facility IDOR Protection:
    Attempting to access, modify, or delete a doctor belonging to another facility
    returns 404 Not Found to prevent resource enumeration and cross-facility leakage.
    """
    permission_classes = [IsFacilityAdmin]
    serializer_class = FacilityDoctorSerializer

    def get_facility(self):
        fac_type, facility = get_facility_for_user(self.request.user)
        if not facility:
            raise PermissionDenied("User is not associated with an authorized medical facility.")
        return fac_type, facility

    def get_object(self):
        fac_type, facility = self.get_facility()
        doctor_id = self.kwargs.get('pk')

        if fac_type == 'hospital':
            doctor = Doctor.objects.filter(id=doctor_id, hospital=facility).select_related(
                'hospital', 'schedule'
            ).first()
        else:
            doctor = Doctor.objects.filter(id=doctor_id, clinic=facility).select_related(
                'clinic', 'schedule'
            ).first()

        if not doctor:
            raise NotFound("Doctor not found in your facility roster.")

        return doctor

    def perform_update(self, serializer):
        doctor = serializer.save()
        log_audit_event(
            action="DOCTOR_UPDATED",
            target_model="Doctor",
            target_id=str(doctor.id),
            actor=self.request.user,
            change_summary={
                "updated_fields": list(serializer.validated_data.keys()),
            },
            request=self.request
        )

    def perform_destroy(self, instance):
        doctor_id = str(instance.id)
        doctor_name = instance.name
        fac_type, facility = self.get_facility()

        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError:
            # Doctor has protected historical appointment/prescription records.
            # Safely de-register and dissociate practitioner from this facility:
            if fac_type == 'hospital':
                instance.hospital = None
            else:
                instance.clinic = None
            instance.status = FacilityStatus.DEACTIVATED
            instance.save(update_fields=['hospital', 'clinic', 'status'])
            if hasattr(instance, 'schedule'):
                try:
                    instance.schedule.delete()
                except Exception:
                    pass

        log_audit_event(
            action="DOCTOR_DELETED",
            target_model="Doctor",
            target_id=doctor_id,
            actor=self.request.user,
            change_summary={
                "name": doctor_name,
                "facility_type": fac_type,
            },
            request=self.request
        )

class FacilityDoctorStatusView(views.APIView):
    """
    Facility administrator doctor status toggling (Active / Deactivated).
    PATCH /api/v1/facility/doctors/{id}/status/
    
    Cross-Facility IDOR Protection:
    Attempting to toggle status for a doctor from another facility returns 404 Not Found.
    """
    permission_classes = [IsFacilityAdmin]

    def patch(self, request, pk):
        fac_type, facility = get_facility_for_user(request.user)
        if not facility:
            raise PermissionDenied("User is not associated with an authorized medical facility.")

        if fac_type == 'hospital':
            doctor = Doctor.objects.filter(id=pk, hospital=facility).first()
        else:
            doctor = Doctor.objects.filter(id=pk, clinic=facility).first()

        if not doctor:
            raise NotFound("Doctor not found in your facility roster.")

        serializer = FacilityDoctorStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        prev_status = doctor.status
        doctor.status = new_status
        doctor.save(update_fields=['status'])

        log_audit_event(
            action="DOCTOR_STATUS_CHANGED",
            target_model="Doctor",
            target_id=str(doctor.id),
            actor=request.user,
            change_summary={
                "previous_status": prev_status,
                "new_status": new_status,
                "doctor_name": doctor.name,
            },
            request=request
        )

        return Response({
            "id": str(doctor.id),
            "name": doctor.name,
            "status": doctor.status,
            "message": f"Doctor status updated to '{new_status}'."
        }, status=status.HTTP_200_OK)
