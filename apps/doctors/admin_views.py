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


class AdminDoctorDetailView(views.APIView):
    """
    Platform administrator detail, edit, and deletion endpoint for individual Doctors.
    GET /api/v1/admin/doctors/{id}/
    PATCH /api/v1/admin/doctors/{id}/
    DELETE /api/v1/admin/doctors/{id}/
    """
    permission_classes = [IsPlatformAdmin]

    def _get_doctor(self, pk):
        try:
            valid_uuid = uuid.UUID(str(pk))
        except (ValueError, TypeError):
            raise NotFound("Doctor not found.")
        doctor = Doctor.objects.filter(id=valid_uuid).select_related(
            'hospital', 'clinic', 'schedule'
        ).first()
        if not doctor:
            raise NotFound("Doctor not found.")
        return doctor

    def get(self, request, pk):
        doctor = self._get_doctor(pk)
        return Response(AdminDoctorListSerializer(doctor).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        doctor = self._get_doctor(pk)
        data = request.data

        # Update basic doctor fields
        if 'name' in data and data['name']:
            doctor.name = data['name'].strip()
        if 'name_ar' in data or 'nameAr' in data:
            doctor.name_ar = (data.get('name_ar') or data.get('nameAr') or '').strip()
        if 'specialty' in data and data['specialty']:
            doctor.specialty = data['specialty'].strip()
        if 'location' in data and data['location']:
            doctor.location = data['location'].strip()
        if 'consultation_fee' in data or 'consultationFee' in data:
            val = data.get('consultation_fee') if 'consultation_fee' in data else data.get('consultationFee')
            doctor.consultation_fee = val if val is not None and val != '' else None
        if 'experience_years' in data or 'experienceYears' in data:
            val = data.get('experience_years') if 'experience_years' in data else data.get('experienceYears')
            try:
                doctor.experience_years = int(val)
                doctor.experience_text = f"{val} years"
                doctor.experience_text_ar = f"{val} سنوات"
            except (ValueError, TypeError):
                pass
        if 'education' in data:
            doctor.education = (data['education'] or '').strip()
        if 'about' in data:
            doctor.about = (data['about'] or '').strip()
        if 'about_ar' in data or 'aboutAr' in data:
            doctor.about_ar = (data.get('about_ar') or data.get('aboutAr') or '').strip()
        if 'photo' in data:
            doctor.photo = data['photo'] or ''
        if 'status' in data and data['status']:
            doctor.status = data['status']

        # Facility Affiliation updates
        if 'hospitalId' in data or 'hospital_id' in data:
            h_id = data.get('hospitalId') or data.get('hospital_id')
            if h_id:
                from apps.facilities.models import Hospital
                hosp = Hospital.objects.filter(id=h_id).first()
                if hosp:
                    doctor.hospital = hosp
                    doctor.clinic = None
            else:
                doctor.hospital = None

        if 'clinicId' in data or 'clinic_id' in data:
            c_id = data.get('clinicId') or data.get('clinic_id')
            if c_id:
                from apps.facilities.models import Clinic
                cln = Clinic.objects.filter(id=c_id).first()
                if cln:
                    doctor.clinic = cln
                    doctor.hospital = None
            else:
                if 'hospitalId' not in data and 'hospital_id' not in data:
                    doctor.clinic = None

        # If both are explicitly null or empty, doctor is independent
        if ('facilityId' in data and not data['facilityId']):
            doctor.hospital = None
            doctor.clinic = None

        doctor.save()

        # Update Schedule if days/slots provided
        available_days = data.get('availableDays') or data.get('available_days')
        standard_slots = data.get('standardSlots') or data.get('standard_slots')
        if available_days or standard_slots:
            from apps.doctors.models import DoctorSchedule
            schedule, _ = DoctorSchedule.objects.get_or_create(doctor=doctor)
            if available_days:
                schedule.available_days = available_days
            if standard_slots:
                schedule.standard_slots = standard_slots
            schedule.save()

        log_audit_event(
            action="DOCTOR_UPDATED",
            target_model="Doctor",
            target_id=str(doctor.id),
            actor=request.user,
            change_summary={"name": doctor.name, "specialty": doctor.specialty},
            request=request
        )

        return Response(AdminDoctorListSerializer(doctor).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        from django.db import transaction
        doctor = self._get_doctor(pk)
        doc_name = doctor.name

        with transaction.atomic():
            if hasattr(doctor, 'appointments'):
                doctor.appointments.all().delete()
            doctor.delete()

        log_audit_event(
            action="DOCTOR_DELETED",
            target_model="Doctor",
            target_id=str(pk),
            actor=request.user,
            change_summary={"name": doc_name},
            request=request
        )

        return Response({"id": str(pk), "message": f"Dr. '{doc_name}' deleted successfully."}, status=status.HTTP_200_OK)


class AdminDoctorBulkActionView(views.APIView):
    """
    Platform administrator bulk actions for Doctors (Verify, Deactivate, Delete).
    POST /api/v1/admin/doctors/bulk-action/
    """
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        from django.db import transaction
        action = request.data.get('action')
        doctor_ids = request.data.get('doctor_ids', [])

        if not action or not isinstance(doctor_ids, list) or len(doctor_ids) == 0:
            return Response({"error": "action and doctor_ids array required."}, status=status.HTTP_400_BAD_REQUEST)

        valid_uuids = []
        for did in doctor_ids:
            try:
                valid_uuids.append(uuid.UUID(str(did)))
            except (ValueError, TypeError):
                continue

        doctors = Doctor.objects.filter(id__in=valid_uuids)
        count = doctors.count()

        if action == 'verify':
            doctors.update(status='Active')
            log_audit_event(
                action="BULK_DOCTORS_VERIFIED",
                target_model="Doctor",
                target_id="bulk",
                actor=request.user,
                change_summary={"count": count, "ids": [str(u) for u in valid_uuids]},
                request=request
            )
            return Response({"message": f"Successfully verified {count} doctors.", "count": count})

        elif action == 'deactivate':
            doctors.update(status='Deactivated')
            log_audit_event(
                action="BULK_DOCTORS_DEACTIVATED",
                target_model="Doctor",
                target_id="bulk",
                actor=request.user,
                change_summary={"count": count, "ids": [str(u) for u in valid_uuids]},
                request=request
            )
            return Response({"message": f"Successfully deactivated {count} doctors.", "count": count})

        elif action == 'delete':
            with transaction.atomic():
                for doc in doctors:
                    if hasattr(doc, 'appointments'):
                        doc.appointments.all().delete()
                    doc.delete()
            log_audit_event(
                action="BULK_DOCTORS_DELETED",
                target_model="Doctor",
                target_id="bulk",
                actor=request.user,
                change_summary={"count": count, "ids": [str(u) for u in valid_uuids]},
                request=request
            )
            return Response({"message": f"Successfully deleted {count} doctors.", "count": count})

        return Response({"error": f"Unknown action: {action}"}, status=status.HTTP_400_BAD_REQUEST)

