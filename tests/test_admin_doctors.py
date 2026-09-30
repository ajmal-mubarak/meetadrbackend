"""Test Suite for Platform Administrator Doctor REST Operations (Phase 11 - Scope A)."""
import uuid
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.audit.models import AuditLog


class PlatformAdminDoctorAPITests(TestCase):
    """Integration test suite for /api/v1/admin/doctors/ and status management."""

    def setUp(self):
        self.client = APIClient()

        # 1. Platform Superadministrator
        self.admin_user = User.objects.create_user(
            email="platform.admin@meetadr.com",
            name="Platform Superadmin",
            password="AdminPassword2026!",
            role=UserRole.ADMIN,
            is_staff=True
        )

        # 2. Staff user without explicit admin role (also platform admin authorized)
        self.staff_user = User.objects.create_user(
            email="staff.user@meetadr.com",
            name="Staff Officer",
            password="StaffPassword2026!",
            role=UserRole.PATIENT,
            is_staff=True
        )

        # 3. Patient User
        self.patient_user = User.objects.create_user(
            email="patient.user@meetadr.com",
            name="Standard Patient",
            password="PatientPassword2026!",
            role=UserRole.PATIENT
        )

        # 4. Doctor User
        self.doctor_user = User.objects.create_user(
            email="doctor.user@meetadr.com",
            name="Dr. Attending",
            password="DoctorPassword2026!",
            role=UserRole.DOCTOR
        )

        # 5. Hospital Facility and Hospital Admin
        self.hospital_admin = User.objects.create_user(
            email="admin@hospital-alpha.com",
            name="Hospital Admin",
            password="HospitalPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.hospital = Hospital.objects.create(
            name="Alpha Specialty Hospital",
            location="Dubai Healthcare City",
            address="Building 10",
            phone="+97140000001",
            operating_hours="24/7",
            status=FacilityStatus.ACTIVE,
            admin_user=self.hospital_admin
        )

        # 6. Clinic Facility and Clinic Admin
        self.clinic_admin = User.objects.create_user(
            email="admin@clinic-beta.com",
            name="Clinic Admin",
            password="ClinicPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.clinic = Clinic.objects.create(
            name="Beta Family Clinic",
            location="Jumeirah, Dubai",
            address="Beach Road",
            primary_specialty="Pediatrics",
            phone="+97140000002",
            operating_hours="09:00 - 18:00",
            status=FacilityStatus.ACTIVE,
            admin_user=self.clinic_admin
        )

        # 7. Doctor at Hospital
        self.hospital_doctor = Doctor.objects.create(
            user=self.doctor_user,
            name="Dr. Sarah Connor",
            name_ar="د. سارة كونور",
            specialty="Cardiology",
            hospital=self.hospital,
            location="Dubai Healthcare City",
            consultation_fee=Decimal("450.00"),
            rating=Decimal("4.90"),
            review_count=18,
            experience_years=12,
            experience_text="12 years experience",
            about="Renowned cardiology specialist.",
            education="MD, FACC",
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.hospital_doctor,
            available_days=["Monday", "Wednesday", "Friday"],
            standard_slots=["09:00 - 09:30", "09:30 - 10:00"]
        )

        # 8. Doctor at Clinic
        self.clinic_doctor_user = User.objects.create_user(
            email="dr.pediatrics@clinic-beta.com",
            name="Dr. Marcus Bell",
            password="DoctorPassword2026!",
            role=UserRole.DOCTOR
        )
        self.clinic_doctor = Doctor.objects.create(
            user=self.clinic_doctor_user,
            name="Dr. Marcus Bell",
            specialty="Pediatrics",
            clinic=self.clinic,
            location="Jumeirah, Dubai",
            consultation_fee=Decimal("300.00"),
            rating=Decimal("4.80"),
            review_count=10,
            experience_years=8,
            about="Board-certified pediatrician.",
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.clinic_doctor,
            available_days=["Tuesday", "Thursday"],
            standard_slots=["10:00 - 10:30", "11:00 - 11:30"]
        )

        # Endpoints
        self.list_url = reverse('admin_onboarding:admin_doctor_list')

    # =========================================================================
    # AUTHORIZATION TESTS — GET /api/v1/admin/doctors/
    # =========================================================================

    def test_01_anonymous_cannot_list_doctors(self):
        """1. Anonymous requests to admin doctor list are rejected with 401."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_02_patient_cannot_list_doctors(self):
        """2. Patient role cannot list admin doctors (403)."""
        self.client.force_authenticate(user=self.patient_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_03_doctor_cannot_list_doctors(self):
        """3. Doctor role cannot list admin doctors (403)."""
        self.client.force_authenticate(user=self.doctor_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_04_hospital_admin_cannot_list_doctors(self):
        """4. Hospital facility administrator cannot list platform-wide admin doctors (403)."""
        self.client.force_authenticate(user=self.hospital_admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_05_clinic_admin_cannot_list_doctors(self):
        """5. Clinic facility administrator cannot list platform-wide admin doctors (403)."""
        self.client.force_authenticate(user=self.clinic_admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_06_platform_admin_can_list_doctors(self):
        """6. Platform superadmin can list doctors platform-wide (200)."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 2)

    def test_07_staff_user_can_list_doctors(self):
        """7. is_staff user is also recognized as platform admin (200)."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    # =========================================================================
    # FUNCTIONAL TESTS — DATA VISIBILITY & COMPATIBILITY
    # =========================================================================

    def test_08_platform_admin_sees_both_hospital_and_clinic_doctors(self):
        """8. Platform-wide listing includes doctors from both Hospitals and Clinics."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']
        doctor_ids = [d['id'] for d in results]
        self.assertIn(str(self.hospital_doctor.id), doctor_ids)
        self.assertIn(str(self.clinic_doctor.id), doctor_ids)

        # Verify hospital doctor facility representation
        hosp_doc_data = next(d for d in results if d['id'] == str(self.hospital_doctor.id))
        self.assertEqual(hosp_doc_data['hospitalName'], "Alpha Specialty Hospital")
        self.assertIsNone(hosp_doc_data['clinicName'])
        self.assertEqual(hosp_doc_data['hospitalId'], str(self.hospital.id))
        self.assertEqual(hosp_doc_data['specialty'], "Cardiology")
        self.assertEqual(hosp_doc_data['experience'], "12 years experience")
        self.assertEqual(hosp_doc_data['availableSlots'], ["09:00 - 09:30", "09:30 - 10:00"])

        # Verify clinic doctor facility representation
        clinic_doc_data = next(d for d in results if d['id'] == str(self.clinic_doctor.id))
        self.assertEqual(clinic_doc_data['clinicName'], "Beta Family Clinic")
        self.assertIsNone(clinic_doc_data['hospitalName'])
        self.assertEqual(clinic_doc_data['clinicId'], str(self.clinic.id))
        self.assertEqual(clinic_doc_data['specialty'], "Pediatrics")
        self.assertEqual(clinic_doc_data['experience'], "8 years")
        self.assertEqual(clinic_doc_data['availableSlots'], ["10:00 - 10:30", "11:00 - 11:30"])

    def test_09_pagination_works_correctly(self):
        """9. Pagination envelope contains count, next, previous, and respects page_size."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.list_url}?page=1&page_size=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNone(response.data['previous'])
        self.assertEqual(len(response.data['results']), 1)

    def test_10_status_filter_works(self):
        """10. Status filter ?status=Deactivated filters appropriately."""
        self.clinic_doctor.status = FacilityStatus.DEACTIVATED
        self.clinic_doctor.save()

        self.client.force_authenticate(user=self.admin_user)

        # Query Active
        res_active = self.client.get(f"{self.list_url}?status=Active")
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        self.assertEqual(res_active.data['count'], 1)
        self.assertEqual(res_active.data['results'][0]['id'], str(self.hospital_doctor.id))

        # Query Deactivated
        res_deact = self.client.get(f"{self.list_url}?status=Deactivated")
        self.assertEqual(res_deact.status_code, status.HTTP_200_OK)
        self.assertEqual(res_deact.data['count'], 1)
        self.assertEqual(res_deact.data['results'][0]['id'], str(self.clinic_doctor.id))

    def test_11_search_filter_works(self):
        """11. Search query parameter filters by doctor name, specialty, or facility."""
        self.client.force_authenticate(user=self.admin_user)

        # Search by specialty
        res_spec = self.client.get(f"{self.list_url}?search=Cardiology")
        self.assertEqual(res_spec.data['count'], 1)
        self.assertEqual(res_spec.data['results'][0]['name'], "Dr. Sarah Connor")

        # Search by facility name
        res_fac = self.client.get(f"{self.list_url}?search=Beta Family")
        self.assertEqual(res_fac.data['count'], 1)
        self.assertEqual(res_fac.data['results'][0]['name'], "Dr. Marcus Bell")

    # =========================================================================
    # DOCTOR STATUS UPDATE — PATCH /api/v1/admin/doctors/<id>/status/
    # =========================================================================

    def test_12_platform_admin_can_deactivate_and_activate_doctor(self):
        """12. Platform admin can toggle doctor status between Active and Deactivated."""
        self.client.force_authenticate(user=self.admin_user)
        status_url = reverse('admin_onboarding:admin_doctor_status', kwargs={'pk': self.hospital_doctor.id})

        # Deactivate
        res_deact = self.client.patch(status_url, {'status': 'Deactivated'}, format='json')
        self.assertEqual(res_deact.status_code, status.HTTP_200_OK)
        self.assertEqual(res_deact.data['status'], 'Deactivated')

        self.hospital_doctor.refresh_from_db()
        self.assertEqual(self.hospital_doctor.status, FacilityStatus.DEACTIVATED)

        # Reactivate
        res_act = self.client.patch(status_url, {'status': 'Active'}, format='json')
        self.assertEqual(res_act.status_code, status.HTTP_200_OK)
        self.assertEqual(res_act.data['status'], 'Active')

        self.hospital_doctor.refresh_from_db()
        self.assertEqual(self.hospital_doctor.status, FacilityStatus.ACTIVE)

    def test_13_invalid_status_choice_is_rejected(self):
        """13. Status values outside FacilityStatus choices are rejected with 400 Bad Request."""
        self.client.force_authenticate(user=self.admin_user)
        status_url = reverse('admin_onboarding:admin_doctor_status', kwargs={'pk': self.hospital_doctor.id})

        response = self.client.patch(status_url, {'status': 'PendingApproval'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.hospital_doctor.refresh_from_db()
        self.assertEqual(self.hospital_doctor.status, FacilityStatus.ACTIVE)

    def test_14_non_admin_roles_cannot_update_doctor_status(self):
        """14. Anonymous, Patient, Doctor, and Facility Admins cannot mutate doctor status."""
        status_url = reverse('admin_onboarding:admin_doctor_status', kwargs={'pk': self.hospital_doctor.id})

        # Anonymous -> 401
        res_anon = self.client.patch(status_url, {'status': 'Deactivated'}, format='json')
        self.assertEqual(res_anon.status_code, status.HTTP_401_UNAUTHORIZED)

        # Patient -> 403
        self.client.force_authenticate(user=self.patient_user)
        res_pat = self.client.patch(status_url, {'status': 'Deactivated'}, format='json')
        self.assertEqual(res_pat.status_code, status.HTTP_403_FORBIDDEN)

        # Doctor -> 403
        self.client.force_authenticate(user=self.doctor_user)
        res_doc = self.client.patch(status_url, {'status': 'Deactivated'}, format='json')
        self.assertEqual(res_doc.status_code, status.HTTP_403_FORBIDDEN)

        # Hospital Admin -> 403
        self.client.force_authenticate(user=self.hospital_admin)
        res_hosp = self.client.patch(status_url, {'status': 'Deactivated'}, format='json')
        self.assertEqual(res_hosp.status_code, status.HTTP_403_FORBIDDEN)

        # Clinic Admin -> 403
        self.client.force_authenticate(user=self.clinic_admin)
        res_clinic = self.client.patch(status_url, {'status': 'Deactivated'}, format='json')
        self.assertEqual(res_clinic.status_code, status.HTTP_403_FORBIDDEN)

    def test_15_status_endpoint_ignores_arbitrary_field_mutations(self):
        """15. Status endpoint cannot be exploited to mutate name, fee, or facility relationships."""
        self.client.force_authenticate(user=self.admin_user)
        status_url = reverse('admin_onboarding:admin_doctor_status', kwargs={'pk': self.hospital_doctor.id})

        payload = {
            'status': 'Deactivated',
            'name': 'Hacked Doctor Name',
            'consultation_fee': Decimal('1.00'),
            'hospital_id': str(uuid.uuid4()),
            'specialty': 'Brain Surgery',
        }
        response = self.client.patch(status_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.hospital_doctor.refresh_from_db()
        self.assertEqual(self.hospital_doctor.status, FacilityStatus.DEACTIVATED)
        self.assertEqual(self.hospital_doctor.name, "Dr. Sarah Connor")
        self.assertEqual(self.hospital_doctor.consultation_fee, Decimal("450.00"))
        self.assertEqual(self.hospital_doctor.specialty, "Cardiology")
        self.assertEqual(self.hospital_doctor.hospital, self.hospital)

    def test_16_nonexistent_doctor_returns_404(self):
        """16. Requesting status update for nonexistent UUID returns 404 Not Found."""
        self.client.force_authenticate(user=self.admin_user)
        fake_url = reverse('admin_onboarding:admin_doctor_status', kwargs={'pk': uuid.uuid4()})
        response = self.client.patch(fake_url, {'status': 'Deactivated'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_17_audit_event_logged_on_status_change(self):
        """17. Immutable audit log entry is created with minimized metadata and no PHI."""
        self.client.force_authenticate(user=self.admin_user)
        status_url = reverse('admin_onboarding:admin_doctor_status', kwargs={'pk': self.hospital_doctor.id})

        self.client.patch(status_url, {'status': 'Deactivated'}, format='json')

        audit_entry = AuditLog.objects.filter(
            action="DOCTOR_STATUS_CHANGED",
            target_model="Doctor",
            target_id=str(self.hospital_doctor.id)
        ).first()

        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.actor, self.admin_user)
        self.assertEqual(audit_entry.change_summary.get('previous_status'), 'Active')
        self.assertEqual(audit_entry.change_summary.get('new_status'), 'Deactivated')
        self.assertEqual(audit_entry.change_summary.get('doctor_name'), 'Dr. Sarah Connor')

        # Strict check: no sensitive credentials, clinical data, or tokens in audit
        summary_str = str(audit_entry.change_summary).lower()
        for forbidden in ['password', 'token', 'secret', 'diagnosis', 'prescription']:
            self.assertNotIn(forbidden, summary_str)

    def test_18_no_sensitive_or_clinical_fields_leaked_in_response(self):
        """18. Doctor list response does not leak user credentials, password hashes, or PHI."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        resp_str = str(response.data).lower()
        for forbidden in ['password', 'token', 'secret', 'hash', 'ssn', 'medical_history']:
            self.assertNotIn(forbidden, resp_str)
