"""Views for facility-scoped administrative management and platform-wide provider oversight."""
from django.db import transaction
from django.db.models import Q, Count, Avg
from rest_framework import views, status, generics
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import UserRole
from apps.accounts.permissions import IsFacilityAdmin, IsPlatformAdmin
from apps.facilities.models import Hospital, Clinic, FacilityDepartment, FacilityStatus
from apps.facilities.facility_serializers import (
    FacilitySettingsSerializer,
    FacilityDepartmentManageSerializer,
    AdminFacilityStatusUpdateSerializer,
    AdminProviderCreateSerializer,
)
from apps.audit.utils import log_audit_event

def get_facility_for_user(user):
    """
    Returns (facility_type, facility_instance) for the authenticated facility administrator.
    
    Security Invariant:
    A facility administrator must belong to exactly ONE facility (Hospital XOR Clinic).
    Authorization fails closed (returns None, None) if:
    - user has no facility
    - user has both hospital and clinic
    - user does not have the 'hospital' role
    """
    if not user or not user.is_authenticated or user.role != UserRole.HOSPITAL:
        return None, None

    has_hosp = hasattr(user, 'hospital_facility') and user.hospital_facility is not None
    has_clinic = hasattr(user, 'clinic_facility') and user.clinic_facility is not None

    if not (has_hosp ^ has_clinic):
        return None, None

    facility = user.hospital_facility if has_hosp else user.clinic_facility
    if facility.status != FacilityStatus.ACTIVE:
        return None, None

    if has_hosp:
        return 'hospital', user.hospital_facility
    return 'clinic', user.clinic_facility

class FacilitySettingsView(views.APIView):
    """
    Authenticated facility administrator inspection and update of their own facility.
    GET /api/v1/facility/settings/
    PATCH /api/v1/facility/settings/
    """
    permission_classes = [IsFacilityAdmin]

    def get(self, request):
        fac_type, facility = get_facility_for_user(request.user)
        if not facility:
            raise PermissionDenied("User is not associated with an authorized medical facility.")

        serializer = FacilitySettingsSerializer(facility)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        fac_type, facility = get_facility_for_user(request.user)
        if not facility:
            raise PermissionDenied("User is not associated with an authorized medical facility.")

        serializer = FacilitySettingsSerializer(facility, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_facility = serializer.save()

        log_audit_event(
            action="FACILITY_UPDATED",
            target_model=facility.__class__.__name__,
            target_id=str(facility.id),
            actor=request.user,
            change_summary={
                "updated_fields": list(serializer.validated_data.keys()),
            },
            request=request
        )

        return Response(FacilitySettingsSerializer(updated_facility).data, status=status.HTTP_200_OK)

    def put(self, request):
        return self.patch(request)

class FacilityDashboardView(views.APIView):
    """
    Operational dashboard KPIs for the authenticated facility administrator.
    GET /api/v1/facility/dashboard/
    """
    permission_classes = [IsFacilityAdmin]

    def get(self, request):
        fac_type, facility = get_facility_for_user(request.user)
        if not facility:
            raise PermissionDenied("User is not associated with an authorized medical facility.")

        doctors_qs = facility.doctors.all()
        total_doctors = doctors_qs.count()
        active_doctors = doctors_qs.filter(status=FacilityStatus.ACTIVE).count()
        deactivated_doctors = doctors_qs.filter(status=FacilityStatus.DEACTIVATED).count()

        # Appointments breakdown
        from apps.appointments.models import Appointment, AppointmentStatus
        if fac_type == 'hospital':
            app_filter = Q(doctor__hospital=facility)
        else:
            app_filter = Q(doctor__clinic=facility)

        apps_qs = Appointment.objects.filter(app_filter)
        total_appointments = apps_qs.count()
        pending_appointments = apps_qs.filter(status=AppointmentStatus.PENDING).count()
        confirmed_appointments = apps_qs.filter(status=AppointmentStatus.CONFIRMED).count()
        completed_appointments = apps_qs.filter(status=AppointmentStatus.COMPLETED).count()
        cancelled_appointments = apps_qs.filter(status=AppointmentStatus.CANCELLED).count()

        return Response({
            "facility_id": str(facility.id),
            "facility_name": facility.name,
            "facility_type": fac_type,
            "facility_status": facility.status,
            "doctors": {
                "total": total_doctors,
                "active": active_doctors,
                "deactivated": deactivated_doctors,
            },
            "appointments": {
                "total": total_appointments,
                "pending": pending_appointments,
                "confirmed": confirmed_appointments,
                "completed": completed_appointments,
                "cancelled": cancelled_appointments,
            }
        }, status=status.HTTP_200_OK)

class FacilityDepartmentListView(views.APIView):
    """
    Hospital clinical departments listing and creation.
    GET /api/v1/hospital/departments/
    POST /api/v1/hospital/departments/
    """
    permission_classes = [IsFacilityAdmin]

    def get(self, request):
        fac_type, facility = get_facility_for_user(request.user)
        if fac_type != 'hospital' or not facility:
            return Response([], status=status.HTTP_200_OK)

        departments = facility.departments.all().order_by('name')
        serializer = FacilityDepartmentManageSerializer(departments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        fac_type, facility = get_facility_for_user(request.user)
        if fac_type != 'hospital' or not facility:
            raise PermissionDenied("Only hospitals can manage clinical departments.")

        serializer = FacilityDepartmentManageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dept = serializer.save(hospital=facility)

        log_audit_event(
            action="DEPARTMENT_CREATED",
            target_model="FacilityDepartment",
            target_id=str(dept.id),
            actor=request.user,
            change_summary={"name": dept.name, "hospital_id": str(facility.id)},
            request=request
        )

        return Response(FacilityDepartmentManageSerializer(dept).data, status=status.HTTP_201_CREATED)

class FacilityDepartmentDetailView(views.APIView):
    """
    Clinical department inspection, update, and deletion for hospital administrators.
    GET /api/v1/facility/departments/{id}/
    PATCH /api/v1/facility/departments/{id}/
    DELETE /api/v1/facility/departments/{id}/
    """
    permission_classes = [IsFacilityAdmin]

    def get(self, request, pk):
        fac_type, facility = get_facility_for_user(request.user)
        if fac_type != 'hospital' or not facility:
            raise PermissionDenied("Only hospitals can manage clinical departments.")

        dept = facility.departments.filter(id=pk).first()
        if not dept:
            raise NotFound("Department not found in your hospital.")

        serializer = FacilityDepartmentManageSerializer(dept)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        fac_type, facility = get_facility_for_user(request.user)
        if fac_type != 'hospital' or not facility:
            raise PermissionDenied("Only hospitals can manage clinical departments.")

        dept = facility.departments.filter(id=pk).first()
        if not dept:
            raise NotFound("Department not found in your hospital.")

        serializer = FacilityDepartmentManageSerializer(dept, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_dept = serializer.save()

        log_audit_event(
            action="DEPARTMENT_UPDATED",
            target_model="FacilityDepartment",
            target_id=str(updated_dept.id),
            actor=request.user,
            change_summary={"name": updated_dept.name, "hospital_id": str(facility.id)},
            request=request
        )

        return Response(FacilityDepartmentManageSerializer(updated_dept).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        fac_type, facility = get_facility_for_user(request.user)
        if fac_type != 'hospital' or not facility:
            raise PermissionDenied("Only hospitals can manage clinical departments.")

        dept = facility.departments.filter(id=pk).first()
        if not dept:
            raise NotFound("Department not found in your hospital.")

        dept_id = str(dept.id)
        dept_name = dept.name
        dept.delete()

        log_audit_event(
            action="DEPARTMENT_DELETED",
            target_model="FacilityDepartment",
            target_id=dept_id,
            actor=request.user,
            change_summary={"name": dept_name, "hospital_id": str(facility.id)},
            request=request
        )

        return Response({"message": "Department deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

class AdminProviderListView(views.APIView):
    """
    Platform administrator listing of all registered Hospitals and Clinics.
    GET /api/v1/admin/providers/
    """
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        provider_type = request.query_params.get('type')
        status_param = request.query_params.get('status')
        search = request.query_params.get('search')

        results = []

        if not provider_type or provider_type.lower() in ['all', 'hospital']:
            hosp_qs = Hospital.objects.all().select_related('admin_user')
            if status_param and status_param.lower() != 'all':
                hosp_qs = hosp_qs.filter(status__iexact=status_param)
            if search:
                q = search.strip()
                hosp_qs = hosp_qs.filter(Q(name__icontains=q) | Q(location__icontains=q))

            for h in hosp_qs:
                rev_agg = h.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
                avg_val = rev_agg.get('avg')
                total_revs = rev_agg.get('count') or 0
                doc_count = h.doctors.count()

                results.append({
                    'id': str(h.id),
                    'type': 'hospital',
                    'name': h.name,
                    'name_ar': h.name_ar,
                    'photo': h.photo or '',
                    'location': h.location,
                    'address': h.address,
                    'phone': h.phone,
                    'google_maps_url': h.google_maps_url or '',
                    'status': h.status,
                    'admin_email': h.admin_user.email if h.admin_user else None,
                    'created_at': h.created_at,
                    'avg_rating': round(float(avg_val), 1) if avg_val is not None else None,
                    'total_reviews': total_revs,
                    'total_doctors': doc_count,
                    'default_available_days': h.default_available_days or [],
                    'default_standard_slots': h.default_standard_slots or [],
                    'defaultAvailableDays': h.default_available_days or [],
                    'defaultStandardSlots': h.default_standard_slots or [],
                })

        if not provider_type or provider_type.lower() in ['all', 'clinic']:
            clinic_qs = Clinic.objects.all().select_related('admin_user')
            if status_param and status_param.lower() != 'all':
                clinic_qs = clinic_qs.filter(status__iexact=status_param)
            if search:
                q = search.strip()
                clinic_qs = clinic_qs.filter(Q(name__icontains=q) | Q(location__icontains=q))

            for c in clinic_qs:
                rev_agg = c.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
                avg_val = rev_agg.get('avg')
                total_revs = rev_agg.get('count') or 0
                doc_count = c.doctors.count()

                results.append({
                    'id': str(c.id),
                    'type': 'clinic',
                    'name': c.name,
                    'name_ar': c.name_ar,
                    'photo': c.photo or '',
                    'location': c.location,
                    'address': c.address,
                    'phone': c.phone,
                    'google_maps_url': c.google_maps_url or '',
                    'status': c.status,
                    'admin_email': c.admin_user.email if c.admin_user else None,
                    'created_at': c.created_at,
                    'avg_rating': round(float(avg_val), 1) if avg_val is not None else None,
                    'total_reviews': total_revs,
                    'total_doctors': doc_count,
                    'default_available_days': c.default_available_days or [],
                    'default_standard_slots': c.default_standard_slots or [],
                    'defaultAvailableDays': c.default_available_days or [],
                    'defaultStandardSlots': c.default_standard_slots or [],
                })

        results.sort(key=lambda x: str(x['name']))
        return Response(results, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminProviderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        p_type = data.get('type', 'hospital')
        name = data['name']
        name_ar = data.get('name_ar') or ''
        photo = data.get('photo') or ''
        location = data.get('location') or 'Dubai'
        address = data.get('address') or f"{location}, UAE"
        address_ar = data.get('address_ar') or ''
        phone = data.get('phone') or '+971 4 000 0000'
        operating_hours = data.get('operating_hours') or 'Open 24/7'
        operating_hours_ar = data.get('operating_hours_ar') or ''
        about = data.get('about') or f"{name} is an accredited medical healthcare provider."
        about_ar = data.get('about_ar') or ''
        google_maps_url = data.get('google_maps_url') or ''

        if p_type == 'hospital':
            facility = Hospital.objects.create(
                name=name,
                name_ar=name_ar,
                photo=photo,
                location=location,
                address=address,
                address_ar=address_ar,
                phone=phone,
                operating_hours=operating_hours,
                operating_hours_ar=operating_hours_ar,
                about=about,
                about_ar=about_ar,
                google_maps_url=google_maps_url,
                emergency_available=data.get('emergency_available', True),
                insurance_plans=data.get('insurance_plans', ''),
                status=FacilityStatus.ACTIVE
            )
        else:
            facility = Clinic.objects.create(
                name=name,
                name_ar=name_ar,
                photo=photo,
                location=location,
                address=address,
                address_ar=address_ar,
                phone=phone,
                operating_hours=operating_hours,
                operating_hours_ar=operating_hours_ar,
                about=about,
                about_ar=about_ar,
                google_maps_url=google_maps_url,
                primary_specialty=data.get('primary_specialty') or 'General Medicine',
                status=FacilityStatus.ACTIVE
            )

        log_audit_event(
            action="FACILITY_CREATED",
            target_model=facility.__class__.__name__,
            target_id=str(facility.id),
            actor=request.user,
            change_summary={"name": facility.name, "type": p_type, "location": facility.location, "google_maps_url": google_maps_url},
            request=request
        )

        return Response({
            'id': str(facility.id),
            'type': p_type,
            'name': facility.name,
            'name_ar': facility.name_ar,
            'photo': facility.photo or '',
            'location': facility.location,
            'address': facility.address,
            'phone': facility.phone,
            'google_maps_url': facility.google_maps_url or '',
            'status': facility.status,
            'admin_email': None,
            'created_at': facility.created_at,
            'avg_rating': None,
            'total_reviews': 0,
            'total_doctors': 0,
            'message': f"{p_type.capitalize()} '{facility.name}' created successfully."
        }, status=status.HTTP_201_CREATED)

class AdminProviderDetailView(views.APIView):
    """
    Platform administrator detail, edit, and deletion endpoint for Hospitals and Clinics.
    GET /api/v1/admin/providers/{id}/
    PATCH /api/v1/admin/providers/{id}/
    DELETE /api/v1/admin/providers/{id}/
    """
    permission_classes = [IsPlatformAdmin]

    def _get_facility(self, pk):
        facility = Hospital.objects.filter(id=pk).first() or Clinic.objects.filter(id=pk).first()
        if not facility:
            raise NotFound("Provider facility not found.")
        return facility

    def get(self, request, pk):
        facility = self._get_facility(pk)
        p_type = 'hospital' if isinstance(facility, Hospital) else 'clinic'
        return Response({
            'id': str(facility.id),
            'type': p_type,
            'name': facility.name,
            'name_ar': facility.name_ar,
            'photo': facility.photo or '',
            'location': facility.location,
            'address': facility.address,
            'address_ar': facility.address_ar if hasattr(facility, 'address_ar') else '',
            'phone': facility.phone,
            'operating_hours': facility.operating_hours,
            'about': facility.about,
            'google_maps_url': facility.google_maps_url or '',
            'status': facility.status,
            'emergency_available': getattr(facility, 'emergency_available', False),
            'insurance_plans': getattr(facility, 'insurance_plans', ''),
            'primary_specialty': getattr(facility, 'primary_specialty', ''),
            'default_available_days': getattr(facility, 'default_available_days', []) or [],
            'default_standard_slots': getattr(facility, 'default_standard_slots', []) or [],
            'defaultAvailableDays': getattr(facility, 'default_available_days', []) or [],
            'defaultStandardSlots': getattr(facility, 'default_standard_slots', []) or [],
        }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        facility = self._get_facility(pk)
        data = request.data

        if 'name' in data and data['name']:
            facility.name = data['name'].strip()
        if 'name_ar' in data:
            facility.name_ar = (data['name_ar'] or '').strip()
        if 'photo' in data:
            facility.photo = data['photo'] or ''
        if 'location' in data and data['location']:
            facility.location = data['location'].strip()
        if 'address' in data:
            facility.address = (data['address'] or '').strip()
        if 'address_ar' in data and hasattr(facility, 'address_ar'):
            facility.address_ar = (data['address_ar'] or '').strip()
        if 'phone' in data:
            facility.phone = (data['phone'] or '').strip()
        if 'operating_hours' in data:
            facility.operating_hours = (data['operating_hours'] or '').strip()
        if 'about' in data:
            facility.about = (data['about'] or '').strip()
        if 'about_ar' in data:
            facility.about_ar = (data['about_ar'] or '').strip()
        if 'google_maps_url' in data:
            facility.google_maps_url = (data['google_maps_url'] or '').strip()
        if 'status' in data and data['status']:
            facility.status = data['status']
        if 'emergency_available' in data and hasattr(facility, 'emergency_available'):
            facility.emergency_available = bool(data['emergency_available'])
        if 'insurance_plans' in data and hasattr(facility, 'insurance_plans'):
            facility.insurance_plans = data['insurance_plans'] or ''
        if 'primary_specialty' in data and hasattr(facility, 'primary_specialty'):
            facility.primary_specialty = data['primary_specialty'] or ''
        if 'default_available_days' in data:
            facility.default_available_days = data['default_available_days'] or []
        elif 'defaultAvailableDays' in data:
            facility.default_available_days = data['defaultAvailableDays'] or []
        if 'default_standard_slots' in data:
            facility.default_standard_slots = data['default_standard_slots'] or []
        elif 'defaultStandardSlots' in data:
            facility.default_standard_slots = data['defaultStandardSlots'] or []

        facility.save()

        p_type = 'hospital' if isinstance(facility, Hospital) else 'clinic'
        log_audit_event(
            action="FACILITY_UPDATED",
            target_model=facility.__class__.__name__,
            target_id=str(pk),
            actor=request.user,
            change_summary={"name": facility.name},
            request=request
        )

        return Response({
            'id': str(facility.id),
            'type': p_type,
            'name': facility.name,
            'name_ar': facility.name_ar,
            'photo': facility.photo or '',
            'location': facility.location,
            'address': facility.address,
            'phone': facility.phone,
            'operating_hours': facility.operating_hours,
            'about': facility.about,
            'google_maps_url': facility.google_maps_url or '',
            'status': facility.status,
            'default_available_days': getattr(facility, 'default_available_days', []) or [],
            'default_standard_slots': getattr(facility, 'default_standard_slots', []) or [],
            'defaultAvailableDays': getattr(facility, 'default_available_days', []) or [],
            'defaultStandardSlots': getattr(facility, 'default_standard_slots', []) or [],
            'message': f"{p_type.capitalize()} '{facility.name}' updated successfully."
        }, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        facility = Hospital.objects.filter(id=pk).first() or Clinic.objects.filter(id=pk).first()
        if not facility:
            raise NotFound("Provider facility not found.")

        fac_name = facility.name
        fac_type = facility.__class__.__name__

        with transaction.atomic():
            # Disassociate doctors and appointments to satisfy PROTECT foreign key constraints
            if hasattr(facility, 'doctors'):
                facility.doctors.update(hospital=None) if isinstance(facility, Hospital) else facility.doctors.update(clinic=None)
            if hasattr(facility, 'appointments'):
                facility.appointments.update(hospital=None) if isinstance(facility, Hospital) else facility.appointments.update(clinic=None)
            facility.delete()

        log_audit_event(
            action="FACILITY_DELETED",
            target_model=fac_type,
            target_id=str(pk),
            actor=request.user,
            change_summary={"name": fac_name},
            request=request
        )

        return Response({
            "id": str(pk),
            "message": f"{fac_type} '{fac_name}' deleted successfully."
        }, status=status.HTTP_200_OK)


class AdminProviderBulkActionView(views.APIView):
    """
    Platform administrator bulk actions for Hospitals and Clinics (Activate, Deactivate, Delete).
    POST /api/v1/admin/providers/bulk-action/
    """
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        action = request.data.get('action')
        provider_ids = request.data.get('provider_ids', [])

        if not action or not isinstance(provider_ids, list) or len(provider_ids) == 0:
            return Response({"error": "action and provider_ids array required."}, status=status.HTTP_400_BAD_REQUEST)

        valid_uuids = []
        for pid in provider_ids:
            try:
                valid_uuids.append(uuid.UUID(str(pid)))
            except (ValueError, TypeError):
                continue

        hospitals = Hospital.objects.filter(id__in=valid_uuids)
        clinics = Clinic.objects.filter(id__in=valid_uuids)
        total_count = hospitals.count() + clinics.count()

        if action == 'activate':
            hospitals.update(status=FacilityStatus.ACTIVE)
            clinics.update(status=FacilityStatus.ACTIVE)
            log_audit_event(
                action="BULK_FACILITIES_ACTIVATED",
                target_model="Facility",
                target_id="bulk",
                actor=request.user,
                change_summary={"count": total_count},
                request=request
            )
            return Response({"message": f"Successfully activated {total_count} facilities.", "count": total_count})

        elif action == 'deactivate':
            hospitals.update(status=FacilityStatus.DEACTIVATED)
            clinics.update(status=FacilityStatus.DEACTIVATED)
            log_audit_event(
                action="BULK_FACILITIES_DEACTIVATED",
                target_model="Facility",
                target_id="bulk",
                actor=request.user,
                change_summary={"count": total_count},
                request=request
            )
            return Response({"message": f"Successfully deactivated {total_count} facilities.", "count": total_count})

        elif action == 'delete':
            with transaction.atomic():
                for h in hospitals:
                    if hasattr(h, 'doctors'):
                        h.doctors.update(hospital=None)
                    if hasattr(h, 'appointments'):
                        h.appointments.update(hospital=None)
                    h.delete()
                for c in clinics:
                    if hasattr(c, 'doctors'):
                        c.doctors.update(clinic=None)
                    if hasattr(c, 'appointments'):
                        c.appointments.update(clinic=None)
                    c.delete()

            log_audit_event(
                action="BULK_FACILITIES_DELETED",
                target_model="Facility",
                target_id="bulk",
                actor=request.user,
                change_summary={"count": total_count},
                request=request
            )
            return Response({"message": f"Successfully deleted {total_count} facilities.", "count": total_count})

        return Response({"error": f"Unknown action: {action}"}, status=status.HTTP_400_BAD_REQUEST)

class AdminProviderStatusView(views.APIView):
    """
    Platform administrator global facility activation/deactivation endpoint.
    PATCH /api/v1/admin/providers/{id}/status/
    """
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        serializer = AdminFacilityStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        facility = Hospital.objects.filter(id=pk).first() or Clinic.objects.filter(id=pk).first()
        if not facility:
            raise NotFound("Provider facility not found.")

        prev_status = facility.status
        facility.status = new_status
        facility.save(update_fields=['status'])

        log_audit_event(
            action="FACILITY_STATUS_CHANGED",
            target_model=facility.__class__.__name__,
            target_id=str(facility.id),
            actor=request.user,
            change_summary={
                "previous_status": prev_status,
                "new_status": new_status,
                "facility_name": facility.name,
            },
            request=request
        )

        return Response({
            "id": str(facility.id),
            "name": facility.name,
            "status": facility.status,
            "message": f"Facility status updated to '{new_status}'."
        }, status=status.HTTP_200_OK)
