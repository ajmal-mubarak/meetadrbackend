"""Views for provider onboarding applications and platform administrative reviews."""
import secrets
import hashlib
from datetime import timedelta
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
from apps.onboarding.models import ProviderRequest, ProviderInvitationToken, ProviderType, RequestStatus
from apps.onboarding.serializers import (
    ProviderRequestPublicCreateSerializer,
    AdminProviderRequestListSerializer,
    AdminProviderRequestStatusUpdateSerializer,
    ProviderRequestPublicStatusSerializer,
)
from apps.onboarding.emails import send_provider_invitation_email
from apps.audit.utils import log_audit_event

class ProviderRequestCreateView(generics.CreateAPIView):
    """
    Public submission endpoint for hospital and clinic partnership onboarding requests.
    POST /api/v1/provider-requests/
    """
    permission_classes = [AllowAny]
    serializer_class = ProviderRequestPublicCreateSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
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
            if app.status == RequestStatus.APPROVED or app.hospital is not None or app.clinic is not None:
                return Response({
                    "error": "ValidationError",
                    "code": "ALREADY_APPROVED",
                    "message": "This onboarding application has already been approved and provisioned."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Atomic provisioning pipeline
            with transaction.atomic():
                admin_email = app.email.lower().strip()
                
                # Verify no conflicting active user exists with a different non-facility role
                existing_user = User.objects.filter(email=admin_email).first()
                if existing_user and existing_user.role not in [UserRole.HOSPITAL]:
                    return Response({
                        "error": "ValidationError",
                        "code": "USER_EMAIL_CONFLICT",
                        "message": f"A user account with email '{admin_email}' already exists with role '{existing_user.role}'."
                    }, status=status.HTTP_400_BAD_REQUEST)

                # 1. Create Facility (Status: 'Deactivated')
                facility = None
                if app.provider_type == ProviderType.HOSPITAL:
                    facility = Hospital.objects.create(
                        name=app.name,
                        name_ar=app.name_ar,
                        location=app.location,
                        address=app.address or app.location,
                        phone=app.contact_number,
                        operating_hours="Mon - Sun: 08:00 - 20:00",
                        about=f"{app.name} is an accredited medical hospital affiliated with MeetAdr.",
                        emergency_available=True,
                        status=FacilityStatus.DEACTIVATED
                    )
                    app.hospital = facility
                    app.clinic = None
                elif app.provider_type == ProviderType.CLINIC:
                    facility = Clinic.objects.create(
                        name=app.name,
                        name_ar=app.name_ar,
                        location=app.location,
                        address=app.address or app.location,
                        primary_specialty="General Medicine",
                        phone=app.contact_number,
                        operating_hours="Mon - Sat: 08:00 - 20:00",
                        about=f"{app.name} is an accredited specialized outpatient clinic affiliated with MeetAdr.",
                        status=FacilityStatus.DEACTIVATED
                    )
                    app.clinic = facility
                    app.hospital = None
                else:
                    return Response({
                        "error": "ValidationError",
                        "code": "INVALID_PROVIDER_TYPE",
                        "message": f"Unsupported provider type '{app.provider_type}'."
                    }, status=status.HTTP_400_BAD_REQUEST)

                # 2. Provision Facility Admin User
                if existing_user:
                    user = existing_user
                    user.name = app.contact_person
                    user.phone = app.contact_number
                    user.role = UserRole.HOSPITAL
                    user.is_active = False
                    user.set_unusable_password()
                    user.save()
                else:
                    user = User.objects.create(
                        email=admin_email,
                        name=app.contact_person,
                        phone=app.contact_number,
                        role=UserRole.HOSPITAL,
                        is_active=False
                    )
                    user.set_unusable_password()
                    user.save()

                # 3. Associate Admin User to Facility
                facility.admin_user = user
                facility.save(update_fields=['admin_user'])

                # 4. Generate Single-Use Cryptographic Setup Token
                raw_token = secrets.token_urlsafe(48)
                token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
                expires_at = timezone.now() + timedelta(hours=72)

                invitation, _ = ProviderInvitationToken.objects.update_or_create(
                    user=user,
                    defaults={
                        'token_hash': token_hash,
                        'expires_at': expires_at,
                        'is_used': False,
                    }
                )

                # 5. Transition Application Status
                app.status = RequestStatus.APPROVED
                app.reviewed_by = request.user
                app.reviewed_at = timezone.now()
                if admin_notes:
                    app.admin_notes = admin_notes
                app.save()

                # 6. Audit Logging (Zero token or credential leakage)
                log_audit_event(
                    action="PROVIDER_APPLICATION_APPROVED",
                    target_model="ProviderRequest",
                    target_id=str(app.id),
                    actor=request.user,
                    change_summary={
                        "provider_type": app.provider_type,
                        "facility_name": app.name,
                        "facility_id": str(facility.id),
                        "admin_email": user.email,
                    },
                    request=request
                )
                log_audit_event(
                    action="FACILITY_CREATED",
                    target_model=facility.__class__.__name__,
                    target_id=str(facility.id),
                    actor=request.user,
                    change_summary={
                        "name": facility.name,
                        "status": facility.status,
                        "admin_user_id": str(user.id),
                    },
                    request=request
                )
                log_audit_event(
                    action="INVITATION_CREATED",
                    target_model="ProviderInvitationToken",
                    target_id=str(invitation.id),
                    actor=request.user,
                    change_summary={
                        "user_id": str(user.id),
                        "user_email": user.email,
                        "facility_id": str(facility.id),
                        "expires_at": expires_at.isoformat(),
                    },
                    request=request
                )

                # 7. Dispatch Email
                send_provider_invitation_email(user, facility, raw_token)

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
