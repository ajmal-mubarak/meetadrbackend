"""Comprehensive Security, Isolation, and Lifecycle Tests for Phase 6.

Covers:
1. Public provider application submission (valid/invalid/rejection of individual doctors)
2. Platform administrator authorization for application review
3. Atomic approval pipeline (Hospital XOR Clinic creation, Deactivated state, single-use invite)
4. Duplicate approval and duplicate facility prevention
5. Rejection pipeline (no facility/user creation)
6. Secure invitation token lifecycle (single-use, expiry, hash storage, replay prevention)
7. Tamper-proof password setup (cannot override role, facility, or userId)
8. Facility isolation and cross-facility IDOR protection (GET, PATCH, DELETE, status)
9. Server-derived facility assignment on doctor creation
10. Strict doctor reassignment prevention
11. Model & database Doctor Hospital XOR Clinic invariant enforcement
12. Facility settings management and mass assignment protection
13. Audit logging security (zero token or credential leakage)
"""
import uuid
import hashlib
import json
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.onboarding.models import ProviderRequest, ProviderInvitationToken, ProviderType, RequestStatus
from apps.audit.models import AuditLog

class ProviderOnboardingAndFacilityManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Platform Superadministrator
        self.admin_user = User.objects.create_user(
            email="platform.admin@meetadr.com",
            name="Super Admin",
            password="AdminPassword2026!",
            role=UserRole.ADMIN,
            is_staff=True
        )

        # 2. Patient User
        self.patient_user = User.objects.create_user(
            email="patient.user@meetadr.com",
            name="Patient Person",
            password="PatientPassword2026!",
            role=UserRole.PATIENT
        )

        # 3. Doctor User
        self.doctor_user = User.objects.create_user(
            email="doctor.user@meetadr.com",
            name="Dr. Ordinary",
            password="DoctorPassword2026!",
            role=UserRole.DOCTOR
        )

        # 4. Facility A (Hospital) & Admin A
        self.admin_a = User.objects.create_user(
            email="admin.a@hospital-a.com",
            name="Admin Hospital A",
            password="HospitalAPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.hospital_a = Hospital.objects.create(
            name="Hospital Alpha",
            location="Dubai Healthcare City",
            address="Building 10, Healthcare City",
            phone="+97140000001",
            operating_hours="08:00 - 20:00",
            emergency_available=True,
            status=FacilityStatus.ACTIVE,
            admin_user=self.admin_a
        )

        # 5. Facility B (Hospital) & Admin B
        self.admin_b = User.objects.create_user(
            email="admin.b@hospital-b.com",
            name="Admin Hospital B",
            password="HospitalBPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.hospital_b = Hospital.objects.create(
            name="Hospital Beta",
            location="Abu Dhabi",
            address="Corniche Road, Abu Dhabi",
            phone="+97120000002",
            operating_hours="08:00 - 20:00",
            emergency_available=False,
            status=FacilityStatus.ACTIVE,
            admin_user=self.admin_b
        )

        # 6. Doctors for Facility A and B
        self.doc_a = Doctor.objects.create(
            name="Dr. Alice Smith",
            specialty="Cardiology",
            hospital=self.hospital_a,
            location=self.hospital_a.location,
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.doc_a,
            available_days=['Monday', 'Wednesday'],
            standard_slots=['09:00 - 09:30', '10:00 - 10:30']
        )

        self.doc_b = Doctor.objects.create(
            name="Dr. Bob Jones",
            specialty="Dermatology",
            hospital=self.hospital_b,
            location=self.hospital_b.location,
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.doc_b,
            available_days=['Tuesday', 'Thursday'],
            standard_slots=['14:00 - 14:30', '15:00 - 15:30']
        )

    # =========================================================================
    # 1. PUBLIC PROVIDER APPLICATION TESTS
    # =========================================================================

    def test_public_hospital_application_succeeds(self):
        """Public applicant can submit a valid Hospital partnership application."""
        url = "/api/v1/provider-requests/"
        payload = {
            "provider_type": "hospital",
            "name": "Al Zahra Medical Center",
            "name_ar": "مركز الزهراء الطبي",
            "contact_person": "Tariq Mansoor",
            "contact_number": "+971509998877",
            "email": "tariq@alzahra.ae",
            "country": "United Arab Emirates",
            "location": "Sharjah",
            "address": "Al Buhaira Corniche, Sharjah",
            "admin_notes": "We would like to partner for cardiology."
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['name'], "Al Zahra Medical Center")

        # Verify DB
        req = ProviderRequest.objects.get(email="tariq@alzahra.ae")
        self.assertEqual(req.status, RequestStatus.PENDING)
        self.assertEqual(req.provider_type, ProviderType.HOSPITAL)
        self.assertIsNone(req.hospital)
        self.assertIsNone(req.clinic)

        # Audit log verified
        self.assertTrue(
            AuditLog.objects.filter(
                action="PROVIDER_APPLICATION_SUBMITTED",
                target_id=str(req.id)
            ).exists()
        )

    def test_public_clinic_application_succeeds(self):
        """Public applicant can submit a valid Clinic partnership application."""
        url = "/api/v1/provider-requests/"
        payload = {
            "provider_type": "clinic",
            "name": "Prime Dental Clinic",
            "contact_person": "Sara Khalid",
            "contact_number": "+971501112233",
            "email": "sara@primedental.ae",
            "location": "Dubai Marina",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['provider_type'], 'clinic')
        self.assertEqual(response.data['status'], 'pending')

    def test_individual_doctor_application_is_strictly_rejected(self):
        """Individual doctors must NOT register through provider onboarding."""
        url = "/api/v1/provider-requests/"
        payload = {
            "provider_type": "doctor",
            "name": "Dr. Independent",
            "contact_person": "Dr. Independent",
            "contact_number": "+971505554433",
            "email": "independent@doctor.com",
            "location": "Dubai",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("provider_type", response.data)

    def test_invalid_application_payloads_rejected(self):
        """Missing required fields or invalid provider types fail validation."""
        url = "/api/v1/provider-requests/"
        # Missing contact details
        response = self.client.post(url, {"provider_type": "hospital", "name": "Only Name"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid email
        response = self.client.post(url, {
            "provider_type": "hospital",
            "name": "Valid Name",
            "contact_person": "Valid Person",
            "contact_number": "+971501234567",
            "email": "not-an-email",
            "location": "Dubai"
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_applicant_cannot_mass_assign_approval_status(self):
        """Applicant cannot submit status='approved' to bypass admin review."""
        url = "/api/v1/provider-requests/"
        payload = {
            "provider_type": "hospital",
            "name": "Sneaky Hospital",
            "contact_person": "Sneaky Person",
            "contact_number": "+971500000000",
            "email": "sneaky@hospital.com",
            "location": "Dubai",
            "status": "approved"
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Server must force status to pending
        self.assertEqual(response.data['status'], 'pending')
        req = ProviderRequest.objects.get(email="sneaky@hospital.com")
        self.assertEqual(req.status, RequestStatus.PENDING)

    # =========================================================================
    # 2. PLATFORM ADMIN AUTHORIZATION & REQUESTS REVIEW
    # =========================================================================

    def test_unauthenticated_cannot_access_admin_requests(self):
        """Unauthenticated requests to admin review endpoints are rejected (401)."""
        res_list = self.client.get("/api/v1/admin/requests/")
        self.assertEqual(res_list.status_code, status.HTTP_401_UNAUTHORIZED)

        res_patch = self.client.patch("/api/v1/admin/requests/00000000-0000-0000-0000-000000000000/status/")
        self.assertEqual(res_patch.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_platform_admins_cannot_access_or_review_requests(self):
        """Patients, doctors, and facility admins cannot approve/reject applications (403)."""
        req = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="Pending Med",
            contact_person="Director",
            contact_number="+971501111111",
            email="pending@med.ae",
            location="Dubai"
        )
        url = f"/api/v1/admin/requests/{req.id}/status/"

        for user in [self.patient_user, self.doctor_user, self.admin_a]:
            self.client.force_authenticate(user=user)
            res_get = self.client.get("/api/v1/admin/requests/")
            self.assertEqual(res_get.status_code, status.HTTP_403_FORBIDDEN)

            res_patch = self.client.patch(url, {"status": "approved"}, format='json')
            self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_admin_can_list_and_filter_requests(self):
        """Platform administrator can view requests with status and keyword filters."""
        ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="Oasis Care Hospital",
            contact_person="Oasis Person",
            contact_number="+971501111111",
            email="oasis@care.ae",
            location="Al Ain",
            status=RequestStatus.PENDING
        )
        ProviderRequest.objects.create(
            provider_type=ProviderType.CLINIC,
            name="Oasis Dental Clinic",
            contact_person="Oasis Dentist",
            contact_number="+971502222222",
            email="dental@care.ae",
            location="Al Ain",
            status=RequestStatus.REJECTED
        )

        self.client.force_authenticate(user=self.admin_user)
        # List all
        res = self.client.get("/api/v1/admin/requests/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data), 2)

        # Filter by status
        res_pending = self.client.get("/api/v1/admin/requests/?status=pending")
        for item in res_pending.data:
            self.assertEqual(item['status'], 'pending')

        # Filter by provider_type
        res_clinic = self.client.get("/api/v1/admin/requests/?type=clinic")
        for item in res_clinic.data:
            self.assertEqual(item['provider_type'], 'clinic')

    # =========================================================================
    # 3. APPROVAL & FACILITY PROVISIONING PIPELINE
    # =========================================================================

    def test_approval_creates_exactly_one_hospital_and_provisions_admin(self):
        """Approving a hospital request creates one Hospital, Deactivated, and dispatches invite."""
        app = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="New Hope Hospital",
            name_ar="مستشفى الأمل الجديد",
            contact_person="Dr. Hope Director",
            contact_number="+971504443322",
            email="director@newhope.ae",
            location="Dubai Healthcare City",
            address="Building 99, DHCC",
            status=RequestStatus.PENDING
        )

        self.client.force_authenticate(user=self.admin_user)
        url = f"/api/v1/admin/requests/{app.id}/status/"
        response = self.client.patch(url, {"status": "approved", "admin_notes": "Licensed DHCC verified"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')

        # 1. Exactly one Hospital created
        hosp = Hospital.objects.filter(name="New Hope Hospital").first()
        self.assertIsNotNone(hosp)
        self.assertEqual(hosp.status, FacilityStatus.DEACTIVATED)
        self.assertEqual(hosp.emergency_available, True)

        # 2. Zero Clinics created
        self.assertFalse(Clinic.objects.filter(name="New Hope Hospital").exists())

        # 3. Facility linked to application
        app.refresh_from_db()
        self.assertEqual(app.status, RequestStatus.APPROVED)
        self.assertEqual(app.hospital, hosp)
        self.assertIsNone(app.clinic)
        self.assertEqual(app.reviewed_by, self.admin_user)
        self.assertIsNotNone(app.reviewed_at)

        # 4. Facility admin User provisioned
        new_admin = User.objects.filter(email="director@newhope.ae").first()
        self.assertIsNotNone(new_admin)
        self.assertEqual(new_admin.role, UserRole.HOSPITAL)
        self.assertEqual(new_admin.is_active, False)
        self.assertFalse(new_admin.has_usable_password())
        self.assertEqual(hosp.admin_user, new_admin)

        # 5. Single-use invitation token created
        invitation = ProviderInvitationToken.objects.filter(user=new_admin).first()
        self.assertIsNotNone(invitation)
        self.assertFalse(invitation.is_used)
        self.assertFalse(invitation.is_expired)

        # 6. Token is NOT returned in API response
        self.assertNotIn('token', json.dumps(response.data, default=str))
        self.assertNotIn(invitation.token_hash, json.dumps(response.data, default=str))

        # 7. Audit log exists and has NO token
        audit_entry = AuditLog.objects.filter(
            action="INVITATION_CREATED",
            target_id=str(invitation.id)
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertNotIn('token', json.dumps(audit_entry.change_summary))
        self.assertNotIn('password', json.dumps(audit_entry.change_summary))

    def test_approval_creates_exactly_one_clinic_for_clinic_request(self):
        """Approving a clinic request creates one Clinic, Deactivated, and zero Hospitals."""
        app = ProviderRequest.objects.create(
            provider_type=ProviderType.CLINIC,
            name="Sunset Polyclinic",
            contact_person="Layla Tariq",
            contact_number="+971507778899",
            email="layla@sunsetclinic.ae",
            location="Jumeirah",
            status=RequestStatus.PENDING
        )

        self.client.force_authenticate(user=self.admin_user)
        url = f"/api/v1/admin/requests/{app.id}/status/"
        response = self.client.patch(url, {"status": "approved"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        clinic = Clinic.objects.filter(name="Sunset Polyclinic").first()
        self.assertIsNotNone(clinic)
        self.assertEqual(clinic.status, FacilityStatus.DEACTIVATED)
        self.assertFalse(Hospital.objects.filter(name="Sunset Polyclinic").exists())

        app.refresh_from_db()
        self.assertEqual(app.clinic, clinic)
        self.assertIsNone(app.hospital)

    def test_repeated_approval_fails_and_prevents_duplicate_provisioning(self):
        """Repeated approval on an already approved application is rejected without duplicate creation."""
        app = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="Single Instance Hospital",
            contact_person="Director",
            contact_number="+971501112233",
            email="single@hospital.ae",
            location="Dubai",
            status=RequestStatus.PENDING
        )

        self.client.force_authenticate(user=self.admin_user)
        url = f"/api/v1/admin/requests/{app.id}/status/"

        # First approval
        res1 = self.client.patch(url, {"status": "approved"}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        initial_hosp_count = Hospital.objects.filter(name="Single Instance Hospital").count()
        initial_user_count = User.objects.filter(email="single@hospital.ae").count()
        initial_token_count = ProviderInvitationToken.objects.filter(user__email="single@hospital.ae").count()

        self.assertEqual(initial_hosp_count, 1)
        self.assertEqual(initial_user_count, 1)
        self.assertEqual(initial_token_count, 1)

        # Second approval attempt
        res2 = self.client.patch(url, {"status": "approved"}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been approved", res2.data['message'])

        # Confirm counts are identical (no duplicates created)
        self.assertEqual(Hospital.objects.filter(name="Single Instance Hospital").count(), 1)
        self.assertEqual(User.objects.filter(email="single@hospital.ae").count(), 1)
        self.assertEqual(ProviderInvitationToken.objects.filter(user__email="single@hospital.ae").count(), 1)

    def test_rejection_does_not_create_facility_or_admin(self):
        """Rejecting an application sets status='rejected' without creating facility or user."""
        app = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="Rejected Health",
            contact_person="Applicant",
            contact_number="+971508889900",
            email="rejected@health.ae",
            location="Sharjah",
            status=RequestStatus.PENDING
        )

        self.client.force_authenticate(user=self.admin_user)
        url = f"/api/v1/admin/requests/{app.id}/status/"
        response = self.client.patch(url, {"status": "rejected", "admin_notes": "Incomplete trade license."}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'rejected')

        app.refresh_from_db()
        self.assertEqual(app.status, RequestStatus.REJECTED)
        self.assertIsNone(app.hospital)
        self.assertIsNone(app.clinic)
        self.assertFalse(Hospital.objects.filter(name="Rejected Health").exists())
        self.assertFalse(User.objects.filter(email="rejected@health.ae").exists())

    def test_cannot_reject_an_already_approved_application(self):
        """Cannot reject an application once it has already been approved and provisioned."""
        app = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="Approved Complex",
            contact_person="Head",
            contact_number="+971501239876",
            email="head@approved.ae",
            location="Dubai",
            status=RequestStatus.PENDING
        )
        self.client.force_authenticate(user=self.admin_user)
        url = f"/api/v1/admin/requests/{app.id}/status/"
        self.client.patch(url, {"status": "approved"}, format='json')

        # Attempt to reject approved app
        res_reject = self.client.patch(url, {"status": "rejected"}, format='json')
        self.assertEqual(res_reject.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # 4. INVITATION & ACCOUNT SETUP TESTS
    # =========================================================================

    def test_invitation_validate_endpoint(self):
        """Token validation endpoint verifies valid, expired, and invalid tokens."""
        raw_token = "secure_random_token_alpha_123456789012345678901234567890"
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

        invite_user = User.objects.create_user(
            email="invitee@test.ae",
            name="Invitee Director",
            role=UserRole.HOSPITAL,
            is_active=False
        )
        hosp = Hospital.objects.create(
            name="Invitee Hospital",
            location="Dubai",
            address="DHCC",
            phone="+971500000000",
            status=FacilityStatus.DEACTIVATED,
            admin_user=invite_user
        )
        invite = ProviderInvitationToken.objects.create(
            user=invite_user,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(hours=72),
            is_used=False
        )

        # 1. Valid token
        res_valid = self.client.post("/api/v1/auth/provider-setup/validate/", {"token": raw_token}, format='json')
        self.assertEqual(res_valid.status_code, status.HTTP_200_OK)
        self.assertTrue(res_valid.data['valid'])
        self.assertEqual(res_valid.data['email'], "invitee@test.ae")
        self.assertEqual(res_valid.data['facility_name'], "Invitee Hospital")
        self.assertEqual(res_valid.data['facility_type'], "hospital")

        # 2. Invalid token
        res_invalid = self.client.post("/api/v1/auth/provider-setup/validate/", {"token": "wrong_token"}, format='json')
        self.assertEqual(res_invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res_invalid.data['valid'])

        # 3. Expired token
        invite.expires_at = timezone.now() - timedelta(minutes=1)
        invite.save()
        res_expired = self.client.post("/api/v1/auth/provider-setup/validate/", {"token": raw_token}, format='json')
        self.assertEqual(res_expired.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res_expired.data['valid'])

        # 4. Consumed token
        invite.expires_at = timezone.now() + timedelta(hours=72)
        invite.is_used = True
        invite.save()
        res_used = self.client.post("/api/v1/auth/provider-setup/validate/", {"token": raw_token}, format='json')
        self.assertEqual(res_used.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res_used.data['valid'])

    def test_invitation_setup_completion_activates_user_and_consumes_token(self):
        """Completing password setup activates administrator and consumes invitation token."""
        raw_token = "completion_token_secure_987654321012345678901234567890"
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

        invite_user = User.objects.create_user(
            email="setup.admin@hospital.ae",
            name="Setup Director",
            role=UserRole.HOSPITAL,
            is_active=False
        )
        invite_user.set_unusable_password()
        invite_user.save()

        Hospital.objects.create(
            name="Setup Hospital",
            location="Dubai",
            address="DHCC",
            phone="+971501234567",
            status=FacilityStatus.DEACTIVATED,
            admin_user=invite_user
        )
        invite = ProviderInvitationToken.objects.create(
            user=invite_user,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(hours=72),
            is_used=False
        )

        url = "/api/v1/auth/provider-setup/complete/"
        payload = {
            "token": raw_token,
            "password": "NewSecurePassword2026!",
            "password_confirm": "NewSecurePassword2026!"
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

        # User is active and has usable password
        invite_user.refresh_from_db()
        self.assertTrue(invite_user.is_active)
        self.assertTrue(invite_user.check_password("NewSecurePassword2026!"))
        self.assertEqual(invite_user.role, UserRole.HOSPITAL)

        # Invitation marked used
        invite.refresh_from_db()
        self.assertTrue(invite.is_used)

        # Replay attempt fails
        res_replay = self.client.post(url, payload, format='json')
        self.assertEqual(res_replay.status_code, status.HTTP_400_BAD_REQUEST)

        # Newly setup user can log in
        login_res = self.client.post("/api/v1/auth/login/", {
            "email": "setup.admin@hospital.ae",
            "password": "NewSecurePassword2026!"
        }, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertEqual(login_res.data['user']['role'], 'hospital')

    def test_setup_cannot_override_role_or_facility_from_request_data(self):
        """Setup payload cannot override role or associate with arbitrary facility."""
        raw_token = "override_test_token_555666777888999000111222333444555"
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

        target_user = User.objects.create_user(
            email="tamper@hospital.ae",
            name="Tamper Person",
            role=UserRole.HOSPITAL,
            is_active=False
        )
        hosp = Hospital.objects.create(
            name="Tamper Hospital",
            location="Dubai",
            address="DHCC",
            phone="+971501112222",
            status=FacilityStatus.DEACTIVATED,
            admin_user=target_user
        )
        ProviderInvitationToken.objects.create(
            user=target_user,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(hours=72),
            is_used=False
        )

        url = "/api/v1/auth/provider-setup/complete/"
        payload = {
            "token": raw_token,
            "password": "ValidPassword2026!",
            "password_confirm": "ValidPassword2026!",
            "role": "admin",  # Tamper attempt
            "hospital_id": str(self.hospital_b.id),  # Tamper attempt
            "clinic_id": str(self.hospital_b.id),
            "is_superuser": True
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        target_user.refresh_from_db()
        self.assertEqual(target_user.role, UserRole.HOSPITAL)
        self.assertFalse(target_user.is_superuser)
        self.assertEqual(target_user.hospital_facility, hosp)

    # =========================================================================
    # 5. FACILITY ISOLATION & CROSS-FACILITY IDOR PROTECTION
    # =========================================================================

    def test_facility_a_admin_can_list_only_own_doctors(self):
        """Facility A administrator only receives Facility A doctors in list."""
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get("/api/v1/facility/doctors/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        doc_ids = [d['id'] for d in res.data]
        self.assertIn(str(self.doc_a.id), doc_ids)
        self.assertNotIn(str(self.doc_b.id), doc_ids)

    def test_facility_b_admin_can_list_only_own_doctors(self):
        """Facility B administrator only receives Facility B doctors in list."""
        self.client.force_authenticate(user=self.admin_b)
        res = self.client.get("/api/v1/facility/doctors/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        doc_ids = [d['id'] for d in res.data]
        self.assertIn(str(self.doc_b.id), doc_ids)
        self.assertNotIn(str(self.doc_a.id), doc_ids)

    def test_cross_facility_idor_retrieve_update_delete_status_all_404(self):
        """
        Facility A admin attempting to retrieve, update, delete, or toggle status
        for Facility B's doctor MUST be denied with 404 Not Found.
        """
        self.client.force_authenticate(user=self.admin_a)
        target_b_id = self.doc_b.id

        # 1. GET /api/v1/facility/doctors/{b_id}/
        res_get_fac = self.client.get(f"/api/v1/facility/doctors/{target_b_id}/")
        self.assertEqual(res_get_fac.status_code, status.HTTP_404_NOT_FOUND)

        # 2. PATCH /api/v1/facility/doctors/{b_id}/
        res_patch_fac = self.client.patch(f"/api/v1/facility/doctors/{target_b_id}/", {"name": "Hacked Dr."}, format='json')
        self.assertEqual(res_patch_fac.status_code, status.HTTP_404_NOT_FOUND)

        # 3. DELETE /api/v1/facility/doctors/{b_id}/
        res_del_fac = self.client.delete(f"/api/v1/facility/doctors/{target_b_id}/")
        self.assertEqual(res_del_fac.status_code, status.HTTP_404_NOT_FOUND)

        # 4. PATCH /api/v1/facility/doctors/{b_id}/status/
        res_stat_fac = self.client.patch(f"/api/v1/facility/doctors/{target_b_id}/status/", {"status": "Deactivated"}, format='json')
        self.assertEqual(res_stat_fac.status_code, status.HTTP_404_NOT_FOUND)

        # 5. Direct /doctor/{b_id}/ aliases
        res_dir_get = self.client.get(f"/api/v1/doctor/{target_b_id}/")
        self.assertEqual(res_dir_get.status_code, status.HTTP_404_NOT_FOUND)

        res_dir_patch = self.client.patch(f"/api/v1/doctor/{target_b_id}/", {"name": "Hacked Dr."}, format='json')
        self.assertEqual(res_dir_patch.status_code, status.HTTP_404_NOT_FOUND)

        res_dir_del = self.client.delete(f"/api/v1/doctor/{target_b_id}/")
        self.assertEqual(res_dir_del.status_code, status.HTTP_404_NOT_FOUND)

        res_dir_stat = self.client.patch(f"/api/v1/doctor/{target_b_id}/status/", {"status": "Deactivated"}, format='json')
        self.assertEqual(res_dir_stat.status_code, status.HTTP_404_NOT_FOUND)

        # Verify Doc B was not modified
        self.doc_b.refresh_from_db()
        self.assertEqual(self.doc_b.name, "Dr. Bob Jones")
        self.assertEqual(self.doc_b.status, FacilityStatus.ACTIVE)

    # =========================================================================
    # 6. DOCTOR MANAGEMENT & FACILITY BINDING
    # =========================================================================

    def test_facility_admin_creates_doctor_server_derives_facility(self):
        """Creating doctor automatically binds authenticated facility and ignores client facility params."""
        self.client.force_authenticate(user=self.admin_a)
        url = "/api/v1/facility/doctors/"
        payload = {
            "name": "Dr. Clara Oswald",
            "specialty": "Neurology",
            "experience_years": 7,
            "hospital_id": str(self.hospital_b.id),  # Client attempts to assign to Facility B
            "clinic_id": str(self.hospital_b.id),
            "facilityId": str(self.hospital_b.id),
            "available_days": ["Monday", "Tuesday"],
            "standard_slots": ["09:00 - 09:30"]
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        new_doc = Doctor.objects.get(name="Dr. Clara Oswald")
        # Derived strictly from request.user (Facility A)
        self.assertEqual(new_doc.hospital, self.hospital_a)
        self.assertIsNone(new_doc.clinic)
        self.assertEqual(new_doc.status, FacilityStatus.ACTIVE)

        # Schedule created
        self.assertEqual(new_doc.schedule.available_days, ["Monday", "Tuesday"])

    def test_doctor_reassignment_rejected(self):
        """Facility admin cannot reassign doctor to another hospital or clinic."""
        self.client.force_authenticate(user=self.admin_a)
        url = f"/api/v1/facility/doctors/{self.doc_a.id}/"
        payload = {
            "hospital": str(self.hospital_b.id),
            "clinic": str(self.hospital_b.id),
            "name": "Dr. Alice Smith Modified"
        }
        res = self.client.patch(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.doc_a.refresh_from_db()
        self.assertEqual(self.doc_a.name, "Dr. Alice Smith Modified")
        # Hospital remains Facility A
        self.assertEqual(self.doc_a.hospital, self.hospital_a)
        self.assertIsNone(self.doc_a.clinic)

    def test_facility_admin_can_toggle_doctor_status(self):
        """Facility admin can toggle their own doctor's Active/Deactivated status."""
        self.client.force_authenticate(user=self.admin_a)
        url = f"/api/v1/facility/doctors/{self.doc_a.id}/status/"

        res_deact = self.client.patch(url, {"status": "Deactivated"}, format='json')
        self.assertEqual(res_deact.status_code, status.HTTP_200_OK)
        self.doc_a.refresh_from_db()
        self.assertEqual(self.doc_a.status, FacilityStatus.DEACTIVATED)

        res_act = self.client.patch(url, {"status": "Active"}, format='json')
        self.assertEqual(res_act.status_code, status.HTTP_200_OK)
        self.doc_a.refresh_from_db()
        self.assertEqual(self.doc_a.status, FacilityStatus.ACTIVE)

    # =========================================================================
    # 7. DOCTOR HOSPITAL XOR CLINIC DOMAIN INVARIANT
    # =========================================================================

    def test_doctor_hospital_xor_clinic_model_validation(self):
        """Model validation strictly enforces Hospital XOR Clinic."""
        # Hospital + Clinic = Invalid
        with self.assertRaises(ValidationError):
            doc = Doctor(
                name="Dr. Invalid Both",
                specialty="General",
                hospital=self.hospital_a,
                clinic=Clinic.objects.create(name="Temp Clinic", location="Dubai", address="Dubai", phone="123")
            )
            doc.clean()

        # Null + Null = Invalid
        with self.assertRaises(ValidationError):
            doc = Doctor(
                name="Dr. Invalid Neither",
                specialty="General",
                hospital=None,
                clinic=None
            )
            doc.clean()

        # Single Hospital = Valid
        doc_valid_hosp = Doctor(
            name="Dr. Valid Hosp",
            specialty="General",
            hospital=self.hospital_a,
            clinic=None
        )
        doc_valid_hosp.clean()  # Does not raise

    # =========================================================================
    # 8. FACILITY SETTINGS & DASHBOARD MANAGEMENT
    # =========================================================================

    def test_facility_settings_management(self):
        """Facility admin can retrieve and update permitted operational fields."""
        self.client.force_authenticate(user=self.admin_a)
        url = "/api/v1/facility/settings/"

        # GET
        res_get = self.client.get(url)
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.data['name'], "Hospital Alpha")

        # PATCH permitted fields
        payload = {
            "name": "Hospital Alpha Premier",
            "phone": "+97149998888",
            "emergency_available": False,
            "status": "Deactivated",  # Client attempts to modify status
            "admin_user": str(self.admin_b.id)  # Client attempts ownership transfer
        }
        res_patch = self.client.patch(url, payload, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data['name'], "Hospital Alpha Premier")
        self.assertEqual(res_patch.data['phone'], "+97149998888")

        self.hospital_a.refresh_from_db()
        self.assertEqual(self.hospital_a.name, "Hospital Alpha Premier")
        # Status and admin_user remain unchanged
        self.assertEqual(self.hospital_a.status, FacilityStatus.ACTIVE)
        self.assertEqual(self.hospital_a.admin_user, self.admin_a)

    def test_facility_dashboard_metrics(self):
        """Facility dashboard returns metrics scoped strictly to facility."""
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get("/api/v1/facility/dashboard/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['facility_id'], str(self.hospital_a.id))
        self.assertIn("doctors", res.data)
        self.assertIn("appointments", res.data)

    # =========================================================================
    # 9. PLATFORM ADMIN PROVIDERS OVERSIGHT
    # =========================================================================

    def test_platform_admin_providers_list_and_status_toggle(self):
        """Platform admin can list all facilities and toggle activation status."""
        self.client.force_authenticate(user=self.admin_user)

        res_list = self.client.get("/api/v1/admin/providers/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res_list.data), 2)

        # Deactivate Hospital Alpha
        url = f"/api/v1/admin/providers/{self.hospital_a.id}/status/"
        res_patch = self.client.patch(url, {"status": "Deactivated"}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)

        self.hospital_a.refresh_from_db()
        self.assertEqual(self.hospital_a.status, FacilityStatus.DEACTIVATED)

    # =========================================================================
    # 10. AUDIT LOG INTEGRITY & ZERO SECRET LEAKAGE
    # =========================================================================

    def test_audit_logs_contain_no_secrets_tokens_or_passwords(self):
        """Audit records never store invitation tokens, JWTs, or passwords."""
        # Trigger an approval which generates an invitation
        app = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="Audit Test Hospital",
            contact_person="Audit Person",
            contact_number="+971501119999",
            email="audit@hospital.ae",
            location="Dubai",
            status=RequestStatus.PENDING
        )
        self.client.force_authenticate(user=self.admin_user)
        self.client.patch(f"/api/v1/admin/requests/{app.id}/status/", {"status": "approved"}, format='json')

        # Inspect all audit logs in the system
        logs = AuditLog.objects.all()
        self.assertGreater(logs.count(), 0)

        forbidden_keys = ['password', 'raw_token', 'token', 'access', 'refresh', 'secret']
        for log_entry in logs:
            summary_str = json.dumps(log_entry.change_summary).lower()
            for key in forbidden_keys:
                # If key appears in summary, its value must be sanitized or not contain a real secret
                if f'"{key}"' in summary_str:
                    val = log_entry.change_summary.get(key)
                    self.assertEqual(val, '[REDACTED]', f"Secret key '{key}' leaked into audit log {log_entry.id}")

            # Verify no 64-char token or raw token leaked
            self.assertNotIn("token_hash", summary_str)
            self.assertNotIn("pbkdf2", summary_str)

    # =========================================================================
    # 11. SECURITY REVIEW FIXES: DEACTIVATION, PRIVACY, IDEMPOTENCY, ISOLATION
    # =========================================================================

    def test_facility_deactivation_enforcement_and_reactivation(self):
        """
        Security Invariant 1:
        When a platform admin deactivates a facility, its administrator cannot
        continue using settings, dashboard, departments, or doctor management.
        Reactivation restores access.
        """
        self.client.force_authenticate(user=self.admin_a)

        # 1. Active: Permitted
        self.assertEqual(self.client.get("/api/v1/facility/settings/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/v1/facility/dashboard/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/v1/facility/doctors/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/v1/facility/departments/").status_code, status.HTTP_200_OK)

        # 2. Platform Admin deactivates Hospital Alpha
        self.hospital_a.status = FacilityStatus.DEACTIVATED
        self.hospital_a.save()

        # 3. Deactivated: Authorization fails closed (403 Forbidden)
        res_settings = self.client.get("/api/v1/facility/settings/")
        self.assertEqual(res_settings.status_code, status.HTTP_403_FORBIDDEN)

        res_patch_settings = self.client.patch("/api/v1/facility/settings/", {"phone": "+97140009999"}, format='json')
        self.assertEqual(res_patch_settings.status_code, status.HTTP_403_FORBIDDEN)

        res_dashboard = self.client.get("/api/v1/facility/dashboard/")
        self.assertEqual(res_dashboard.status_code, status.HTTP_403_FORBIDDEN)

        res_doctors = self.client.get("/api/v1/facility/doctors/")
        self.assertEqual(res_doctors.status_code, status.HTTP_403_FORBIDDEN)

        res_post_doctor = self.client.post("/api/v1/facility/doctors/", {
            "name": "Dr. Blocked",
            "specialty": "Pediatrics"
        }, format='json')
        self.assertEqual(res_post_doctor.status_code, status.HTTP_403_FORBIDDEN)

        res_status = self.client.patch(f"/api/v1/doctor/{self.doc_a.id}/status/", {"status": "Deactivated"}, format='json')
        self.assertEqual(res_status.status_code, status.HTTP_403_FORBIDDEN)

        res_dept = self.client.get("/api/v1/facility/departments/")
        self.assertEqual(res_dept.status_code, status.HTTP_403_FORBIDDEN)

        res_post_dept = self.client.post("/api/v1/facility/departments/", {
            "name": "Cardiology Department",
            "head_of_department": "Dr. Alice Smith"
        }, format='json')
        self.assertEqual(res_post_dept.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Reactivation restores access
        self.hospital_a.status = FacilityStatus.ACTIVE
        self.hospital_a.save()

        self.assertEqual(self.client.get("/api/v1/facility/settings/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/v1/facility/dashboard/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/v1/facility/doctors/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/v1/facility/departments/").status_code, status.HTTP_200_OK)

    def test_public_provider_request_status_privacy(self):
        """
        Security Invariant 2:
        Public GET /api/v1/provider-requests/<id>/ must not expose sensitive applicant
        data, contact numbers, email, notes, review actor, or internal facility IDs.
        Random UUID must return 404 without leaking info.
        """
        app = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="Confidential Medical Complex",
            contact_person="Dr. Secret Applicant",
            contact_number="+971509998877",
            email="confidential@applicant.ae",
            location="Abu Dhabi",
            address="Private Villa 42",
            admin_notes="Applicant background check in progress.",
            status=RequestStatus.PENDING
        )

        # 1. Anonymous query of valid application
        url = f"/api/v1/provider-requests/{app.id}/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Permitted non-sensitive fields
        self.assertEqual(res.data['id'], str(app.id))
        self.assertEqual(res.data['provider_type'], 'hospital')
        self.assertEqual(res.data['status'], 'pending')
        self.assertIn('submitted_at', res.data)

        # Strictly forbidden private fields
        forbidden_fields = [
            'email',
            'contact_number',
            'contact_person',
            'address',
            'admin_notes',
            'reviewed_by',
            'reviewed_by_email',
            'rejection_reason',
            'hospital',
            'clinic',
            'facility_id',
            'facility_name',
        ]
        for field in forbidden_fields:
            self.assertNotIn(field, res.data, f"Private field '{field}' leaked in public status response!")

        # 2. Anonymous query of unknown UUID returns 404 without leakage
        random_uuid = uuid.uuid4()
        res_404 = self.client.get(f"/api/v1/provider-requests/{random_uuid}/")
        self.assertEqual(res_404.status_code, status.HTTP_404_NOT_FOUND)

    def test_provider_invitation_throttling_and_generic_failure(self):
        """
        Security Invariant 3:
        Invitation endpoints have throttle_scope='auth' and return uniform, generic
        error messages on invalid, expired, or used tokens to prevent enumeration.
        """
        from apps.accounts.views import ProviderSetupValidateView, ProviderSetupCompleteView
        self.assertEqual(ProviderSetupValidateView.throttle_scope, 'auth')
        self.assertEqual(ProviderSetupCompleteView.throttle_scope, 'auth')

        # 1. Random invalid token
        res_invalid = self.client.post("/api/v1/auth/provider-setup/validate/", {"token": "random_fake_token"}, format='json')
        self.assertEqual(res_invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_invalid.data['error'], 'InvalidInvitation')
        self.assertIn("Invalid, expired, or previously consumed", res_invalid.data['message'])

        # 2. Expired token
        raw_token = "expired_token_for_generic_test_111222333444555"
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        u = User.objects.create_user(email="exp@test.com", name="Exp User", role=UserRole.HOSPITAL, is_active=False)
        ProviderInvitationToken.objects.create(
            user=u,
            token_hash=token_hash,
            expires_at=timezone.now() - timedelta(hours=1),
            is_used=False
        )
        res_expired = self.client.post("/api/v1/auth/provider-setup/validate/", {"token": raw_token}, format='json')
        self.assertEqual(res_expired.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_expired.data['error'], 'InvalidInvitation')
        self.assertEqual(res_expired.data['message'], res_invalid.data['message'])

        # 3. Consumed token
        raw_token_used = "used_token_for_generic_test_666777888999000"
        token_hash_used = hashlib.sha256(raw_token_used.encode('utf-8')).hexdigest()
        u_used = User.objects.create_user(email="used@test.com", name="Used User", role=UserRole.HOSPITAL, is_active=False)
        ProviderInvitationToken.objects.create(
            user=u_used,
            token_hash=token_hash_used,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=True
        )
        res_used = self.client.post("/api/v1/auth/provider-setup/validate/", {"token": raw_token_used}, format='json')
        self.assertEqual(res_used.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_used.data['error'], 'InvalidInvitation')
        self.assertEqual(res_used.data['message'], res_invalid.data['message'])

        # 4. Same uniform message on complete endpoint
        res_complete_bad = self.client.post("/api/v1/auth/provider-setup/complete/", {
            "token": "fake_token",
            "password": "ValidPassword2026!",
            "password_confirm": "ValidPassword2026!"
        }, format='json')
        self.assertEqual(res_complete_bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_complete_bad.data['error'], 'InvalidInvitation')

    def test_approval_state_machine_comprehensive_idempotency(self):
        """
        Security Invariant 4:
        State machine enforces:
        - pending -> rejected (no facility created)
        - rejected -> rejected (idempotent, no side effects)
        - rejected -> approved (transitions safely without duplicates)
        - approved -> approved (fails with 400, no duplicates)
        - approved -> rejected (fails with 400)
        """
        self.client.force_authenticate(user=self.admin_user)

        app = ProviderRequest.objects.create(
            provider_type=ProviderType.HOSPITAL,
            name="State Transition Hospital",
            contact_person="Director Transition",
            contact_number="+971501112233",
            email="transition@hospital.ae",
            location="Dubai",
            status=RequestStatus.PENDING
        )
        url = f"/api/v1/admin/requests/{app.id}/status/"

        # 1. pending -> rejected
        res_rej = self.client.patch(url, {"status": "rejected", "admin_notes": "First rejection."}, format='json')
        self.assertEqual(res_rej.status_code, status.HTTP_200_OK)
        app.refresh_from_db()
        self.assertEqual(app.status, RequestStatus.REJECTED)
        self.assertIsNone(app.hospital)
        self.assertIsNone(app.clinic)
        self.assertEqual(Hospital.objects.filter(name="State Transition Hospital").count(), 0)

        # 2. rejected -> rejected (idempotent)
        res_rej_again = self.client.patch(url, {"status": "rejected", "admin_notes": "Second rejection note."}, format='json')
        self.assertEqual(res_rej_again.status_code, status.HTTP_200_OK)
        self.assertEqual(Hospital.objects.filter(name="State Transition Hospital").count(), 0)

        # 3. rejected -> approved (safe transition, creates exactly one facility and admin)
        res_app = self.client.patch(url, {"status": "approved"}, format='json')
        self.assertEqual(res_app.status_code, status.HTTP_200_OK)
        app.refresh_from_db()
        self.assertEqual(app.status, RequestStatus.APPROVED)
        self.assertIsNotNone(app.hospital)
        self.assertIsNone(app.clinic)
        self.assertEqual(Hospital.objects.filter(name="State Transition Hospital").count(), 1)
        self.assertEqual(User.objects.filter(email="transition@hospital.ae").count(), 1)
        self.assertEqual(ProviderInvitationToken.objects.filter(user__email="transition@hospital.ae").count(), 1)

        # 4. approved -> approved (blocked, duplicate prevention)
        res_dup_app = self.client.patch(url, {"status": "approved"}, format='json')
        self.assertEqual(res_dup_app.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_dup_app.data['code'], 'ALREADY_APPROVED')
        self.assertEqual(Hospital.objects.filter(name="State Transition Hospital").count(), 1)
        self.assertEqual(User.objects.filter(email="transition@hospital.ae").count(), 1)

        # 5. approved -> rejected (blocked)
        res_rej_after_app = self.client.patch(url, {"status": "rejected"}, format='json')
        self.assertEqual(res_rej_after_app.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_rej_after_app.data['code'], 'CANNOT_REJECT_APPROVED')

    def test_department_crud_and_cross_facility_isolation(self):
        """
        Security Invariant 6:
        Facility A admin can create, list, retrieve, update, delete own departments.
        Facility B admin attempting to access Facility A's department receives 404 Not Found.
        """
        # 1. Admin A creates Department in Hospital Alpha
        self.client.force_authenticate(user=self.admin_a)
        res_create = self.client.post("/api/v1/facility/departments/", {
            "name": "Neurology Department",
            "head_of_department": "Dr. Sarah Conner"
        }, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        dept_id = res_create.data['id']

        # 2. Admin A lists departments: own department present
        res_list = self.client.get("/api/v1/facility/departments/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        dept_ids = [d['id'] for d in res_list.data]
        self.assertIn(dept_id, dept_ids)

        # 3. Admin A updates own department: 200 OK
        res_patch = self.client.patch(f"/api/v1/facility/departments/{dept_id}/", {
            "head_of_department": "Dr. Sarah Conner, MD"
        }, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data['head_of_department'], "Dr. Sarah Conner, MD")

        # 4. Cross-facility IDOR: Admin B attempts to access Admin A's department
        self.client.force_authenticate(user=self.admin_b)
        
        # GET -> 404
        res_b_get = self.client.get(f"/api/v1/facility/departments/{dept_id}/")
        self.assertEqual(res_b_get.status_code, status.HTTP_404_NOT_FOUND)

        # PATCH -> 404
        res_b_patch = self.client.patch(f"/api/v1/facility/departments/{dept_id}/", {
            "name": "Hacked Department"
        }, format='json')
        self.assertEqual(res_b_patch.status_code, status.HTTP_404_NOT_FOUND)

        # DELETE -> 404
        res_b_del = self.client.delete(f"/api/v1/facility/departments/{dept_id}/")
        self.assertEqual(res_b_del.status_code, status.HTTP_404_NOT_FOUND)

        # Verify department still exists and untouched
        from apps.facilities.models import FacilityDepartment
        dept_obj = FacilityDepartment.objects.get(id=dept_id)
        self.assertEqual(dept_obj.name, "Neurology Department")
        self.assertEqual(dept_obj.hospital, self.hospital_a)

        # 5. Admin A deletes own department -> 204 No Content
        self.client.force_authenticate(user=self.admin_a)
        res_del = self.client.delete(f"/api/v1/facility/departments/{dept_id}/")
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FacilityDepartment.objects.filter(id=dept_id).exists())
