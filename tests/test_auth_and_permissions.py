"""Authentication, Token Lifecycle, Session Ceiling and Authorization Tests."""
import time
from datetime import date
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import UntypedToken

from apps.accounts.models import User, UserRole, PatientProfile, PatientDependent, BloodGroup, RelationType
from apps.accounts.tokens import MeetAdrRefreshToken
from apps.facilities.models import Hospital
from apps.doctors.models import Doctor
from apps.appointments.models import Appointment, AppointmentStatus
from apps.audit.models import AuditLog

class AuthenticationAndPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patient_password = "SecurePassword2026!"
        self.patient_user = User.objects.create_user(
            email="patient@example.com",
            name="Jane Doe",
            password=self.patient_password,
            phone="+971501234567",
            role=UserRole.PATIENT
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user,
            gender="Female",
            dob=date(1995, 5, 20),
            blood_group=BloodGroup.O_POS
        )

        # Hospital & Doctor setup for clinical access tests
        self.hospital = Hospital.objects.create(
            name="Apollo Speciality Hospital",
            name_ar="مستشفى أبولو التخصصي",
            location="Dubai Healthcare City",
            address="Building 64, Dubai",
            phone="+97143876543",
            operating_hours="24/7",
            about="Premier tertiary healthcare facility."
        )
        self.doctor_user = User.objects.create_user(
            email="dr.smith@example.com",
            name="Dr. John Smith",
            password="DoctorPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            name="Dr. John Smith",
            hospital=self.hospital,
            specialty="Cardiology",
            experience_years=12,
            location="Dubai",
            consultation_fee=350.00
        )

    def test_patient_registration_success(self):
        """Registering a new patient creates User + PatientProfile and returns JWTs."""
        payload = {
            "name": "Sarah Connor",
            "email": "sarah@resistance.org",
            "password": "StrongPassword2026!",
            "phone": "+971550001122"
        }
        response = self.client.post(reverse('accounts:register'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['role'], 'patient')
        self.assertTrue('meetadr_refresh_token' in response.cookies)

        # Verify database state
        user = User.objects.get(email="sarah@resistance.org")
        self.assertEqual(user.role, UserRole.PATIENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(hasattr(user, 'patient_profile'))

    def test_privilege_escalation_blocked_on_registration(self):
        """Attempting to assign admin role or staff status during registration is ignored."""
        payload = {
            "name": "Attacker Account",
            "email": "attacker@evil.com",
            "password": "StrongPassword2026!",
            "role": "admin",
            "is_staff": True,
            "is_superuser": True
        }
        response = self.client.post(reverse('accounts:register'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="attacker@evil.com")
        self.assertEqual(user.role, UserRole.PATIENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_password_policy_enforcement(self):
        """Weak or short passwords must be rejected with 400 Bad Request."""
        payload = {
            "name": "Weak Password User",
            "email": "weak@example.com",
            "password": "short"
        }
        response = self.client.post(reverse('accounts:register'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_login_success_and_jwt_claims(self):
        """Successful login returns custom access token claims and sets HttpOnly cookie."""
        payload = {
            "email": "patient@example.com",
            "password": self.patient_password
        }
        response = self.client.post(reverse('accounts:login'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('meetadr_refresh_token', response.cookies)

        # Inspect token claims
        access_token = UntypedToken(response.data['access'])
        self.assertEqual(access_token['email'], "patient@example.com")
        self.assertEqual(access_token['role'], "patient")
        self.assertEqual(access_token['user_id'], str(self.patient_user.id))

    def test_token_refresh_and_rotation(self):
        """Token refresh exchanges refresh token for a rotated one and invalidates the old one."""
        # 1. Login to get initial refresh token
        login_res = self.client.post(reverse('accounts:login'), {
            "email": "patient@example.com",
            "password": self.patient_password
        }, format='json')
        initial_refresh = login_res.data['refresh']

        # 2. Call token refresh
        refresh_res = self.client.post(reverse('accounts:token_refresh'), {
            "refresh": initial_refresh
        }, format='json')
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        new_access = refresh_res.data['access']
        new_refresh = refresh_res.data['refresh']
        self.assertNotEqual(initial_refresh, new_refresh)

        # 3. Attempt to reuse initial refresh token -> must fail due to rotation blacklist
        reuse_res = self.client.post(reverse('accounts:token_refresh'), {
            "refresh": initial_refresh
        }, format='json')
        self.assertIn(reuse_res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST])

    def test_session_ceiling_30_days_enforcement(self):
        """Tokens past the 30-day session maximum ceiling are rejected upon refresh."""
        # Generate token with session_start_iat backdated 31 days
        thirty_one_days_ago = int(time.time()) - (31 * 86400)
        expired_session_token = MeetAdrRefreshToken.for_user(
            self.patient_user,
            session_start_iat=thirty_one_days_ago
        )

        response = self.client.post(reverse('accounts:token_refresh'), {
            "refresh": str(expired_session_token)
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get('code'), 'SESSION_EXPIRED')

    def test_logout_blacklists_token_and_clears_cookie(self):
        """Logout blacklists the active refresh token and clears cookie."""
        login_res = self.client.post(reverse('accounts:login'), {
            "email": "patient@example.com",
            "password": self.patient_password
        }, format='json')
        refresh_token = login_res.data['refresh']

        logout_res = self.client.post(reverse('accounts:logout'), {
            "refresh": refresh_token
        }, format='json')
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # Verify old token cannot refresh
        refresh_res = self.client.post(reverse('accounts:token_refresh'), {
            "refresh": refresh_token
        }, format='json')
        self.assertEqual(refresh_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_me_endpoint(self):
        """GET /api/v1/auth/me/ returns authenticated user and clinical profile."""
        token = MeetAdrRefreshToken.for_user(self.patient_user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get(reverse('accounts:current_user'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.patient_user.email)
        self.assertIn('patient_profile', response.data)
        self.assertEqual(response.data['patient_profile']['blood_group'], 'O+')

    def test_patient_profile_and_dependent_crud(self):
        """Patient can manage their medical profile and CRUD family dependents."""
        token = MeetAdrRefreshToken.for_user(self.patient_user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # 1. Update own profile
        profile_res = self.client.patch(reverse('patients:patient_profile'), {
            "allergies": "Penicillin",
            "insurance_provider": "Daman Health",
            "insurance_number": "DAMAN-98765"
        }, format='json')
        self.assertEqual(profile_res.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_res.data['allergies'], "Penicillin")

        # 2. Add dependent
        dep_res = self.client.post(reverse('patients:patient_dependents_list'), {
            "name": "Tommy Doe",
            "relation": RelationType.CHILD,
            "gender": "Male",
            "blood_group": BloodGroup.O_POS,
            "allergies": "Peanuts"
        }, format='json')
        self.assertEqual(dep_res.status_code, status.HTTP_201_CREATED)
        dep_id = dep_res.data['id']

        # 3. List dependents
        list_res = self.client.get(reverse('patients:patient_dependents_list'))
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)
        self.assertEqual(list_res.data[0]['name'], "Tommy Doe")

        # 4. Delete dependent
        del_res = self.client.delete(reverse('patients:patient_dependent_detail', kwargs={'pk': dep_id}))
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(PatientDependent.objects.count(), 0)

    def test_idor_protection_dependents(self):
        """Patient B cannot access or modify Patient A's dependent (returns 404)."""
        # Create Patient A dependent
        dep_a = PatientDependent.objects.create(
            profile=self.patient_profile,
            name="Alice Doe",
            relation=RelationType.CHILD
        )

        # Create Patient B
        patient_b = User.objects.create_user(
            email="patient_b@example.com",
            name="Patient B",
            password="StrongPassword2026!",
            role=UserRole.PATIENT
        )
        PatientProfile.objects.create(user=patient_b)

        token_b = MeetAdrRefreshToken.for_user(patient_b).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_b}')

        # Patient B tries to get Patient A's dependent
        get_res = self.client.get(reverse('patients:patient_dependent_detail', kwargs={'pk': dep_a.id}))
        self.assertEqual(get_res.status_code, status.HTTP_404_NOT_FOUND)

        # Patient B tries to delete Patient A's dependent
        del_res = self.client.delete(reverse('patients:patient_dependent_detail', kwargs={'pk': dep_a.id}))
        self.assertEqual(del_res.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_patient_clinical_relationship_access(self):
        """Doctor cannot view patient chart without confirmed/completed appointment."""
        doctor_token = MeetAdrRefreshToken.for_user(self.doctor_user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {doctor_token}')

        url = reverse('doctors:doctor_patient_profile', kwargs={'patient_id': self.patient_profile.id})

        # 1. No appointment exists -> 404
        res1 = self.client.get(url)
        self.assertEqual(res1.status_code, status.HTTP_404_NOT_FOUND)

        # 2. Cancelled appointment exists -> 404
        apt = Appointment.objects.create(
            doctor=self.doctor,
            hospital=self.hospital,
            patient_profile=self.patient_profile,
            booked_by=self.patient_user,
            patient_name_snapshot="Jane Doe",
            specialty_snapshot="Cardiology",
            date=date(2026, 10, 1),
            time_slot="10:00 AM",
            status=AppointmentStatus.CANCELLED
        )
        res2 = self.client.get(url)
        self.assertEqual(res2.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Confirmed appointment exists -> 200 OK
        apt.status = AppointmentStatus.CONFIRMED
        apt.save()
        res3 = self.client.get(url)
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.data['blood_group'], 'O+')

    def test_audit_logging_data_minimization(self):
        """Audit logging captures login and security actions without logging sensitive passwords."""
        self.client.post(reverse('accounts:login'), {
            "email": "patient@example.com",
            "password": self.patient_password
        }, format='json')

        login_log = AuditLog.objects.filter(action='USER_LOGIN_SUCCESS').first()
        self.assertIsNotNone(login_log)
        self.assertNotIn('password', login_log.change_summary)
        self.assertNotIn('token', login_log.change_summary)
