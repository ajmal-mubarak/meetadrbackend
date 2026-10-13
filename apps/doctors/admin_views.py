"""Platform Administrator Doctor Management Views."""
import uuid
from django.db.models import Q
from rest_framework import generics, views, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination

from apps.accounts.permissions import IsPlatformAdmin
from apps.doctors.models import Doctor
from apps.doctors.serializers import (
    AdminDoctorListSerializer,
    AdminDoctorCreateSerializer,
    AdminDoctorStatusUpdateSerializer,
)
from apps.audit.utils import log_audit_event


class AdminDoctorPagination(PageNumberPagination):
    """Platform administrator doctor directory pagination."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminDoctorListView(generics.ListCreateAPIView):
    """
    Platform administrator listing and creation of Doctors.
    GET /api/v1/admin/doctors/
    POST /api/v1/admin/doctors/
    """
    permission_classes = [IsPlatformAdmin]
    pagination_class = AdminDoctorPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminDoctorCreateSerializer
        return AdminDoctorListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = serializer.save()

        log_audit_event(
            action="DOCTOR_CREATED",
            target_model="Doctor",
            target_id=str(doctor.id),
            actor=request.user,
            change_summary={
                "name": doctor.name,
                "specialty": doctor.specialty,
                "location": doctor.location,
                "hospital": doctor.hospital.name if doctor.hospital else None,
                "clinic": doctor.clinic.name if doctor.clinic else None,
            },
            request=request
        )

        output_serializer = AdminDoctorListSerializer(doctor)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        queryset = Doctor.objects.all().select_related(
            'hospital', 'clinic', 'schedule'
        )

        status_param = self.request.query_params.get('status')
        if status_param and status_param.lower() != 'all':
            queryset = queryset.filter(status__iexact=status_param.strip())

        search = self.request.query_params.get('search')
        if search:
            q = search.strip()
            filter_q = (
                Q(name__icontains=q) |
                Q(specialty__icontains=q) |
                Q(hospital__name__icontains=q) |
                Q(clinic__name__icontains=q) |
                Q(location__icontains=q)
            )
            try:
                uuid_val = uuid.UUID(q)
                filter_q |= Q(id=uuid_val)
            except (ValueError, TypeError):
                pass
            queryset = queryset.filter(filter_q)

        return queryset.order_by('name')


class AdminDoctorStatusView(views.APIView):
    """
    Platform administrator doctor activation/deactivation endpoint.
    PATCH /api/v1/admin/doctors/{id}/status/
    """
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        try:
            valid_uuid = uuid.UUID(str(pk))
        except (ValueError, TypeError):
            raise NotFound("Doctor not found.")

        doctor = Doctor.objects.filter(id=valid_uuid).select_related(
            'hospital', 'clinic', 'schedule'
        ).first()
        if not doctor:
            raise NotFound("Doctor not found.")

        serializer = AdminDoctorStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        previous_status = doctor.status
        doctor.status = new_status
        doctor.save(update_fields=['status', 'updated_at'])

        log_audit_event(
            action="DOCTOR_STATUS_CHANGED",
            target_model="Doctor",
            target_id=str(doctor.id),
            actor=request.user,
            change_summary={
                "previous_status": previous_status,
                "new_status": new_status,
                "doctor_name": doctor.name,
                "facility_name": doctor.hospital.name if doctor.hospital else (
                    doctor.clinic.name if doctor.clinic else "Unassigned"
                ),
            },
            request=request
        )

        return Response(AdminDoctorListSerializer(doctor).data, status=status.HTTP_200_OK)
