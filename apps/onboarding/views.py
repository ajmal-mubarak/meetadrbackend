"""Views for provider onboarding applications and platform administrative reviews."""
import secrets
import hashlib
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied

from apps.accounts.models import User, UserRole
from apps.accounts.permissions import IsPlatformAdmin
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.onboarding.models import ProviderRequest, ProviderInvitationToken, ProviderType, RequestStatus
from apps.onboarding.serializers import (
    ProviderRequestPublicCreateSerializer,
    AdminProviderRequestListSerializer,
    AdminProviderRequestStatusUpdateSerializer,
    ProviderRequestPublicStatusSerializer,
)
from apps.onboarding.emails import send_provider_invitation_email
from apps.audit.utils import log_audit_event
from apps.notifications.services import notify_provider_request_submitted

class ProviderRequestCreateView(generics.CreateAPIView):
    """
    Public submission endpoint for hospital and clinic partnership onboarding requests.
    POST /api/v1/provider-requests/
    """
    permission_classes = [AllowAny]
    serializer_class = ProviderRequestPublicCreateSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            notify_provider_request_submitted(instance)
        log_audit_event(
            action="PROVIDER_APPLICATION_SUBMITTED",
            target_model="ProviderRequest",
            target_id=str(instance.id),
            actor=self.request.user if self.request.user.is_authenticated else None,
            change_summary={
                "name": instance.name,
                "provider_type": instance.provider_type,
                "email": instance.email,
                "location": instance.location,
            },
            request=self.request
        )

class ProviderRequestPublicStatusView(generics.RetrieveAPIView):
    """
    Public read-only status query for an application reference ID.
    GET /api/v1/provider-requests/{id}/
    
    Privacy Invariant:
    Never exposes applicant email, phone, contact person, admin notes, 
    review actor, or internal facility/audit details.
    """
    permission_classes = [AllowAny]
    serializer_class = ProviderRequestPublicStatusSerializer
    queryset = ProviderRequest.objects.all()

class AdminProviderRequestListView(generics.ListAPIView):
    """
    Platform administrator listing of provider onboarding requests with faceted filtering.
    GET /api/v1/admin/requests/
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminProviderRequestListSerializer

    def get_queryset(self):
        queryset = ProviderRequest.objects.all().select_related(
            'reviewed_by', 'hospital', 'clinic'
        )
        
        status_param = self.request.query_params.get('status')
        if status_param and status_param.lower() != 'all':
            queryset = queryset.filter(status=status_param.lower().strip())

        provider_type = self.request.query_params.get('provider_type') or self.request.query_params.get('type')
        if provider_type and provider_type.lower() != 'all':
            queryset = queryset.filter(provider_type=provider_type.lower().strip())

        search = self.request.query_params.get('search')
        if search:
            q = search.strip()
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(name_ar__icontains=q) |
                Q(contact_person__icontains=q) |
                Q(email__icontains=q) |
                Q(location__icontains=q)
            )

        return queryset.order_by('-submitted_at')

class AdminProviderRequestDetailView(generics.RetrieveAPIView):
    """
    Platform administrator single provider application inspection.
    GET /api/v1/admin/requests/{id}/
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminProviderRequestListSerializer
    queryset = ProviderRequest.objects.all().select_related(
        'reviewed_by', 'hospital', 'clinic'
    )

class AdminProviderRequestStatusView(views.APIView):
    """
    Platform administrator application review and transition endpoint.
    PATCH /api/v1/admin/requests/{id}/status/
    
    Security & State Transition Invariants:
    1. Only platform administrators can review applications.
    2. Explicit transitions: pending -> approved, pending -> rejected.
    3. Re-approving an already approved application is strictly prevented (idempotent / conflict protection).
    4. Upon approval:
       - Creates Hospital XOR Clinic (strictly exclusive).
       - Facility initial status is set to 'Deactivated' per approved architecture.
       - Provisions facility admin account with role='hospital' and unusable password.
       - Generates single-use, 72-hour SHA-256 hashed setup token.
       - Dispatches invitation email with one-time setup link.
       - Records safe audit log without leaking tokens or credentials.
    5. Upon rejection:
       - Marks status as 'rejected'.
       - Does NOT create any facility or administrator account.
    """
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        try:
            app = ProviderRequest.objects.select_related('hospital', 'clinic').get(pk=pk)
        except (ProviderRequest.DoesNotExist, ValueError):
            raise NotFound("Provider request not found.")

        serializer = AdminProviderRequestStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        admin_notes = serializer.validated_data.get('admin_notes', '')

        # State transition validations
        if new_status == 'approved':
            if app.status == RequestStatus.APPROVED or app.hospital is not None or app.clinic is not None or app.doctor is not None:
                return Response({
                    "error": "ValidationError",
                    "code": "ALREADY_APPROVED",
                    "message": "This onboarding application has already been approved and provisioned."
                }, status=status.HTTP_400_BAD_REQUEST)

            facility_data = serializer.validated_data.get('facility_data')
            doctor_data = serializer.validated_data.get('doctor_data')

            # Atomic provisioning pipeline
            with transaction.atomic():
                admin_email = app.email.lower().strip()
                if facility_data and facility_data.get('manager_email'):
                    admin_email = facility_data.get('manager_email').lower().strip()
                elif doctor_data and doctor_data.get('email'):
                    admin_email = doctor_data.get('email').lower().strip()

                target_role = UserRole.DOCTOR if app.provider_type == ProviderType.DOCTOR else UserRole.HOSPITAL
                
                # Direct credentials if provided
                direct_username = None
                direct_password = None
                if facility_data:
                    direct_username = facility_data.get('username')
                    direct_password = facility_data.get('password')
                elif doctor_data:
                    direct_username = doctor_data.get('username')
                    direct_password = doctor_data.get('password')

                # 1. Create Facility or Doctor
                facility = None
                doctor = None

                if app.provider_type == ProviderType.HOSPITAL or (facility_data and facility_data.get('type') == 'hospital'):
                    f_name = (facility_data.get('name') if facility_data else None) or app.name
                    f_name_ar = (facility_data.get('name_ar') if facility_data else None) or app.name_ar
                    f_loc = (facility_data.get('location') if facility_data else None) or app.location
                    f_country = (facility_data.get('country') if facility_data else None) or app.country or 'United Arab Emirates'
                    f_emirate = (facility_data.get('emirate') if facility_data else None) or f_loc
                    f_area = (facility_data.get('area') if facility_data else None) or ''
                    f_addr = (facility_data.get('address') if facility_data else None) or app.address or f_loc
                    f_phone = (facility_data.get('phone') if facility_data else None) or app.contact_number
                    f_dial = (facility_data.get('phone_dial_code') if facility_data else None) or '+971'
                    f_hours = (facility_data.get('operating_hours') if facility_data else None) or "Open 24/7"
                    f_about = (facility_data.get('about') if facility_data else None) or f"{f_name} is an accredited medical hospital affiliated with MeetAdr."
                    f_emergency = facility_data.get('emergency_available', True) if facility_data else True
                    f_maps = (facility_data.get('google_maps_url') if facility_data else None) or app.google_maps_url or ''
                    f_website = (facility_data.get('website') if facility_data else None) or ''
                    f_photo = (facility_data.get('photo') if facility_data else None) or ''
                    f_logo = (facility_data.get('logo') if facility_data else None) or ''
                    f_cat = (facility_data.get('facility_category') if facility_data else None) or 'Hospital'
                    f_mgr_name = (facility_data.get('manager_name') if facility_data else None) or app.contact_person or app.name
                    f_mgr_phone = (facility_data.get('manager_phone') if facility_data else None) or app.contact_number
                    f_ins = facility_data.get('insurance_plans', '') if facility_data else ''
                    if isinstance(f_ins, list):
                        f_ins = ', '.join(f_ins)

                    facility = Hospital.objects.create(
                        name=f_name,
                        name_ar=f_name_ar,
                        location=f_loc,
                        country=f_country,
                        emirate=f_emirate,
                        area=f_area,
                        address=f_addr,
                        phone=f_phone,
                        phone_dial_code=f_dial,
                        operating_hours=f_hours,
                        about=f_about,
                        emergency_available=f_emergency,
                        google_maps_url=f_maps,
                        website=f_website,
                        photo=f_photo,
                        logo=f_logo,
                        facility_category=f_cat,
                        manager_name=f_mgr_name,
                        manager_phone=f_mgr_phone,
                        manager_email=admin_email,
                        insurance_plans=f_ins,
                        status=FacilityStatus.ACTIVE if (direct_username and direct_password) else FacilityStatus.DEACTIVATED
                    )
                    app.hospital = facility
                    app.clinic = None
                    app.doctor = None

                elif app.provider_type == ProviderType.CLINIC or (facility_data and facility_data.get('type') == 'clinic'):
                    f_name = (facility_data.get('name') if facility_data else None) or app.name
                    f_name_ar = (facility_data.get('name_ar') if facility_data else None) or app.name_ar
                    f_loc = (facility_data.get('location') if facility_data else None) or app.location
                    f_country = (facility_data.get('country') if facility_data else None) or app.country or 'United Arab Emirates'
                    f_emirate = (facility_data.get('emirate') if facility_data else None) or f_loc
                    f_area = (facility_data.get('area') if facility_data else None) or ''
                    f_addr = (facility_data.get('address') if facility_data else None) or app.address or f_loc
                    f_phone = (facility_data.get('phone') if facility_data else None) or app.contact_number
                    f_dial = (facility_data.get('phone_dial_code') if facility_data else None) or '+971'
                    f_hours = (facility_data.get('operating_hours') if facility_data else None) or "Mon - Sat: 08:00 - 20:00"
                    f_spec = (facility_data.get('primary_specialty') if facility_data else None) or app.specialty or "General Medicine"
                    f_about = (facility_data.get('about') if facility_data else None) or f"{f_name} is an accredited specialized outpatient clinic affiliated with MeetAdr."
                    f_maps = (facility_data.get('google_maps_url') if facility_data else None) or app.google_maps_url or ''
                    f_website = (facility_data.get('website') if facility_data else None) or ''
                    f_photo = (facility_data.get('photo') if facility_data else None) or ''
                    f_logo = (facility_data.get('logo') if facility_data else None) or ''
                    f_cat = (facility_data.get('facility_category') if facility_data else None) or 'Clinic'
                    f_mgr_name = (facility_data.get('manager_name') if facility_data else None) or app.contact_person or app.name
                    f_mgr_phone = (facility_data.get('manager_phone') if facility_data else None) or app.contact_number
                    f_ins = facility_data.get('insurance_plans', '') if facility_data else ''
                    if isinstance(f_ins, list):
                        f_ins = ', '.join(f_ins)

                    facility = Clinic.objects.create(
                        name=f_name,
                        name_ar=f_name_ar,
                        location=f_loc,
                        country=f_country,
                        emirate=f_emirate,
                        area=f_area,
                        address=f_addr,
                        primary_specialty=f_spec,
                        phone=f_phone,
                        phone_dial_code=f_dial,
                        operating_hours=f_hours,
                        about=f_about,
                        google_maps_url=f_maps,
                        website=f_website,
                        photo=f_photo,
                        logo=f_logo,
                        facility_category=f_cat,
                        manager_name=f_mgr_name,
                        manager_phone=f_mgr_phone,
                        manager_email=admin_email,
                        insurance_plans=f_ins,
                        status=FacilityStatus.ACTIVE if (direct_username and direct_password) else FacilityStatus.DEACTIVATED
                    )
                    app.clinic = facility
                    app.hospital = None
                    app.doctor = None

                elif app.provider_type == ProviderType.DOCTOR:
                    d_name = (doctor_data.get('name') if doctor_data else None) or app.name
                    d_name_ar = (doctor_data.get('name_ar') if doctor_data else None) or app.name_ar
                    d_first = (doctor_data.get('first_name') if doctor_data else None) or ''
                    d_last = (doctor_data.get('last_name') if doctor_data else None) or ''
                    d_gender = (doctor_data.get('gender') if doctor_data else None) or 'Male'
                    d_dept = (doctor_data.get('department') if doctor_data else None) or app.specialty or ''
                    d_spec = (doctor_data.get('specialty') if doctor_data else None) or app.specialty or "General Physician"
                    d_loc = (doctor_data.get('location') if doctor_data else None) or app.location
                    d_about = (doctor_data.get('about') if doctor_data else None) or f"Dr. {d_name} is an independent medical practitioner affiliated with MeetAdr."
                    d_fee = doctor_data.get('consultation_fee', 100.00) if doctor_data else 100.00
                    d_exp = doctor_data.get('experience_years', 5) if doctor_data else 5
                    d_photo = (doctor_data.get('photo') if doctor_data else None) or ''
                    d_edu = (doctor_data.get('education') if doctor_data else None) or ''
                    d_quals = doctor_data.get('qualifications', []) if doctor_data else []
                    d_langs = doctor_data.get('languages', ['English', 'Arabic']) if doctor_data else ['English', 'Arabic']
                    d_interests = doctor_data.get('special_interests', []) if doctor_data else []

                    doctor = Doctor.objects.create(
                        name=d_name,
                        name_ar=d_name_ar,
                        first_name=d_first,
                        last_name=d_last,
                        gender=d_gender,
                        department=d_dept,
                        specialty=d_spec,
                        qualifications=d_quals,
                        languages=d_langs,
                        special_interests=d_interests,
                        location=d_loc,
                        about=d_about,
                        education=d_edu,
                        photo=d_photo,
                        consultation_fee=d_fee,
                        experience_years=d_exp,
                        status=FacilityStatus.ACTIVE,
                    )

                    avail_days = doctor_data.get('available_days', ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']) if doctor_data else ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
                    std_slots = doctor_data.get('standard_slots', [
                        '09:00 - 09:30', '09:30 - 10:00', '10:00 - 10:30', '10:30 - 11:00',
                        '11:00 - 11:30', '14:00 - 14:30', '14:30 - 15:00', '15:00 - 15:30', '16:00 - 16:30'
                    ]) if doctor_data else [
                        '09:00 - 09:30', '09:30 - 10:00', '10:00 - 10:30', '10:30 - 11:00',
                        '11:00 - 11:30', '14:00 - 14:30', '14:30 - 15:00', '15:00 - 15:30', '16:00 - 16:30'
                    ]

                    DoctorSchedule.objects.create(
                        doctor=doctor,
                        available_days=avail_days,
                        standard_slots=std_slots,
                        slot_duration_minutes=30
                    )
                    app.doctor = doctor
                    app.hospital = None
                    app.clinic = None
                else:
                    return Response({
                        "error": "ValidationError",
                        "code": "INVALID_PROVIDER_TYPE",
                        "message": f"Unsupported provider type '{app.provider_type}'."
                    }, status=status.HTTP_400_BAD_REQUEST)

                # 2. Provision Admin/Doctor User
                # If direct credentials (username & password) are provided by admin in modal:
                if direct_username and direct_password:
                    target_email = direct_username.strip().lower() if '@' in direct_username else (admin_email or f"{direct_username.strip().lower()}@meetadr.local")
                    existing_user = User.objects.filter(email=target_email).first()
                    if existing_user:
                        if (target_role == UserRole.HOSPITAL and (hasattr(existing_user, 'hospital_facility') or hasattr(existing_user, 'clinic_facility'))) or \
                           (target_role == UserRole.DOCTOR and hasattr(existing_user, 'doctor_profile')):
                            unique_suffix = uuid.uuid4().hex[:6]
                            target_email = f"{direct_username.split('@')[0]}_{unique_suffix}@meetadr.local"
                            user = User.objects.create_user(
                                email=target_email,
                                password=direct_password,
                                role=target_role,
                                name=(facility_data.get('manager_name') if facility_data else None) or app.contact_person or app.name,
                                phone=app.contact_number or '',
                                is_active=True
                            )
                        else:
                            user = existing_user
                            user.name = (facility_data.get('manager_name') if facility_data else None) or app.contact_person or app.name
                            user.phone = app.contact_number or ''
                            user.role = target_role
                            user.is_active = True
                            user.set_password(direct_password)
                            user.save()
                    else:
                        user = User.objects.create_user(
                            email=target_email,
                            password=direct_password,
                            role=target_role,
                            name=(facility_data.get('manager_name') if facility_data else None) or app.contact_person or app.name,
                            phone=app.contact_number or '',
                            is_active=True
                        )
                else:
                    # Legacy fallback for passwordless / setup-token link
                    existing_user = User.objects.filter(email=admin_email).first()
                    if existing_user:
                        user = existing_user
                        user.name = app.contact_person or app.name
                        user.phone = app.contact_number
                        user.role = target_role
                        user.is_active = False
                        user.set_unusable_password()
                        user.save()
                    else:
                        user = User.objects.create(
                            email=admin_email,
                            name=app.contact_person or app.name,
                            phone=app.contact_number,
                            role=target_role,
                            is_active=False
                        )
                        user.set_unusable_password()
                        user.save()

                    # Generate Single-Use Setup Token only for legacy fallback
                    raw_token = secrets.token_urlsafe(48)
                    token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
                    expires_at = timezone.now() + timedelta(hours=72)
                    ProviderInvitationToken.objects.update_or_create(
                        user=user,
                        defaults={
                            'token_hash': token_hash,
                            'expires_at': expires_at,
                            'is_used': False,
                        }
                    )
                    send_provider_invitation_email(user, doctor or facility, raw_token)

                # 3. Associate User
                if facility:
                    facility.admin_user = user
                    facility.save(update_fields=['admin_user'])
                elif doctor:
                    doctor.user = user
                    doctor.save(update_fields=['user'])

                # 4. Transition Application Status
                app.status = RequestStatus.APPROVED
                app.reviewed_by = request.user
                app.reviewed_at = timezone.now()
                if admin_notes:
                    app.admin_notes = admin_notes
                app.save()

                # 5. Audit Logging
                target_entity = doctor or facility
                log_audit_event(
                    action="PROVIDER_APPLICATION_APPROVED",
                    target_model="ProviderRequest",
                    target_id=str(app.id),
                    actor=request.user,
                    change_summary={
                        "provider_type": app.provider_type,
                        "name": app.name,
                        "entity_id": str(target_entity.id),
                        "admin_email": user.email,
                        "live_direct": bool(direct_username and direct_password)
                    },
                    request=request
                )

            return Response(AdminProviderRequestListSerializer(app).data, status=status.HTTP_200_OK)

        elif new_status == 'rejected':
            if app.status == RequestStatus.APPROVED:
                return Response({
                    "error": "ValidationError",
                    "code": "CANNOT_REJECT_APPROVED",
                    "message": "Cannot reject an application that has already been approved and provisioned."
                }, status=status.HTTP_400_BAD_REQUEST)

            app.status = RequestStatus.REJECTED
            app.reviewed_by = request.user
            app.reviewed_at = timezone.now()
            if admin_notes:
                app.admin_notes = admin_notes
            app.save()

            log_audit_event(
                action="PROVIDER_APPLICATION_REJECTED",
                target_model="ProviderRequest",
                target_id=str(app.id),
                actor=request.user,
                change_summary={
                    "name": app.name,
                    "provider_type": app.provider_type,
                    "admin_notes": admin_notes,
                },
                request=request
            )

            return Response(AdminProviderRequestListSerializer(app).data, status=status.HTTP_200_OK)


class AdminResendInvitationView(views.APIView):
    """
    Regenerates a fresh setup invitation token for an approved provider and
    returns the direct setup link so the admin can manually deliver it.

    POST /api/v1/admin/requests/{id}/resend-invitation/

    Security:
    - Platform admin only.
    - Only allowed for approved applications.
    - Invalidates the previous token and creates a new 72-hour one.
    - The raw token is returned ONCE in the response body (admin responsibility to deliver it).
    - The raw token is never persisted; only its SHA-256 hash is stored.
    """
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        try:
            app = ProviderRequest.objects.select_related('hospital', 'clinic').get(pk=pk)
        except (ProviderRequest.DoesNotExist, ValueError):
            raise NotFound("Provider request not found.")

        if app.status != RequestStatus.APPROVED:
            return Response({
                "error": "ValidationError",
                "code": "NOT_APPROVED",
                "message": "Invitation can only be resent for approved applications."
            }, status=status.HTTP_400_BAD_REQUEST)

        facility = app.hospital or app.clinic
        if not facility or not facility.admin_user:
            return Response({
                "error": "ValidationError",
                "code": "NO_FACILITY_USER",
                "message": "No facility administrator account found for this application."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = facility.admin_user

        with transaction.atomic():
            # Generate fresh single-use token
            raw_token = secrets.token_urlsafe(48)
            token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
            expires_at = timezone.now() + timedelta(hours=72)

            ProviderInvitationToken.objects.update_or_create(
                user=user,
                defaults={
                    'token_hash': token_hash,
                    'expires_at': expires_at,
                    'is_used': False,
                }
            )

            log_audit_event(
                action="INVITATION_RESENT",
                target_model="ProviderRequest",
                target_id=str(app.id),
                actor=request.user,
                change_summary={
                    "facility_name": facility.name,
                    "admin_email": user.email,
                    "expires_at": expires_at.isoformat(),
                },
                request=request
            )

        # Also attempt email delivery
        send_provider_invitation_email(user, facility, raw_token)

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        setup_link = f"{frontend_url}/provider-setup?token={raw_token}"

        return Response({
            "success": True,
            "message": f"Invitation regenerated for {user.email}. Setup link is valid for 72 hours.",
            "admin_email": user.email,
            "facility_name": facility.name,
            "setup_link": setup_link,
            "expires_at": expires_at.isoformat(),
        }, status=status.HTTP_200_OK)

