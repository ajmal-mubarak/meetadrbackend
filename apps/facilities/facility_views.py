"""Views for facility-scoped administrative management and platform-wide provider oversight."""
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
                    'status': h.status,
                    'admin_email': h.admin_user.email if h.admin_user else None,
                    'created_at': h.created_at,
                    'avg_rating': round(float(avg_val), 1) if avg_val is not None else None,
                    'total_reviews': total_revs,
                    'total_doctors': doc_count,
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
                    'status': c.status,
                    'admin_email': c.admin_user.email if c.admin_user else None,
                    'created_at': c.created_at,
                    'avg_rating': round(float(avg_val), 1) if avg_val is not None else None,
                    'total_reviews': total_revs,
                    'total_doctors': doc_count,
                })

        results.sort(key=lambda x: str(x['name']))
        return Response(results, status=status.HTTP_200_OK)

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
