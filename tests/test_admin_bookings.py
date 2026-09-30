"""Test Suite for Platform Administrator Global Bookings REST Operations (Phase 11 - Scope B)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole, PatientProfile
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus
from apps.notifications.models import Notification
from apps.audit.models import AuditLog


class PlatformAdminBookingAPITests(TestCase):
    """Integration test suite for /api/v1/admin/bookings/ and admin cancellation."""

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

        # 2. Staff user (platform admin authorized via is_staff)
        self.staff_user = User.objects.create_user(
            email="staff.officer@meetadr.com",
            name="Staff Officer",
            password="StaffPassword2026!",
            role=UserRole.PATIENT,
            is_staff=True
        )

        # 3. Patient Users
        self.patient_a = User.objects.create_user(
            email="patient.a@example.com",
            name="Alice Patient",
            phone="+971501111111",
            password="PatientPassword2026!",
            role=UserRole.PATIENT
        )
        self.profile_a = PatientProfile.objects.create(
            user=self.patient_a,
            gender="Female",
            dob=date(1992, 4, 15)
        )

        self.patient_b = User.objects.create_user(
            email="patient.b@example.com",
            name="Bob Patient",
            phone="+971502222222",
            password="PatientPassword2026!",
            role=UserRole.PATIENT
        )
        self.profile_b = PatientProfile.objects.create(
            user=self.patient_b,
            gender="Male",
            dob=date(1988, 8, 20)
        )

        # 4. Doctors & Facilities (Hospital & Clinic)
        self.hosp_admin = User.objects.create_user(
            email="admin@hospital-x.com",
            name="Hospital Admin",
            password="HospitalPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.hospital = Hospital.objects.create(
            name="Oasis Specialty Hospital",
            location="Dubai Healthcare City",
            address="Building 22",
            phone="+97140001111",
            operating_hours="24/7",
            status=FacilityStatus.ACTIVE,
            admin_user=self.hosp_admin
        )

        self.doc_hosp_user = User.objects.create_user(
            email="dr.hosp@oasis.ae",
            name="Dr. Zayd Mansoor",
            password="DoctorPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doc_hosp = Doctor.objects.create(
            user=self.doc_hosp_user,
            name="Dr. Zayd Mansoor",
            specialty="Cardiology",
            hospital=self.hospital,
            location="Dubai Healthcare City",
            consultation_fee=Decimal("400.00"),
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.doc_hosp,
            available_days=["Monday", "Tuesday"],
            standard_slots=["09:00 - 09:30", "10:00 - 10:30"]
        )

        self.clinic_admin = User.objects.create_user(
            email="admin@clinic-y.com",
            name="Clinic Admin",
            password="ClinicPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.clinic = Clinic.objects.create(
            name="Sunrise Family Clinic",
            location="Jumeirah, Dubai",
            address="Al Wasl Road",
            primary_specialty="Dermatology",
            phone="+97140002222",
            operating_hours="09:00 - 19:00",
            status=FacilityStatus.ACTIVE,
            admin_user=self.clinic_admin
        )

        self.doc_clinic_user = User.objects.create_user(
            email="dr.clinic@sunrise.ae",
            name="Dr. Layla Nour",
            password="DoctorPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doc_clinic = Doctor.objects.create(
            user=self.doc_clinic_user,
            name="Dr. Layla Nour",
            specialty="Dermatology",
            clinic=self.clinic,
            location="Jumeirah, Dubai",
            consultation_fee=Decimal("350.00"),
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.doc_clinic,
            available_days=["Wednesday", "Thursday"],
            standard_slots=["14:00 - 14:30", "15:00 - 15:30"]
        )

        # 5. Seed Appointments
        # Appointment 1: Confirmed at Hospital
        self.appt_hosp = Appointment.objects.create(
            booked_by=self.patient_a,
            patient_profile=self.profile_a,
            doctor=self.doc_hosp,
            hospital=self.hospital,
            patient_name_snapshot="Alice Patient",
            patient_phone_snapshot="+971501111111",
            patient_email_snapshot="patient.a@example.com",
            specialty_snapshot="Cardiology",
            date=date.today() + timedelta(days=2),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.CONFIRMED,
            notes="Routine heart check"
        )

        # Appointment 2: Confirmed at Clinic
        self.appt_clinic = Appointment.objects.create(
            booked_by=self.patient_b,
            patient_profile=self.profile_b,
            doctor=self.doc_clinic,
            clinic=self.clinic,
            patient_name_snapshot="Bob Patient",
            patient_phone_snapshot="+971502222222",
            patient_email_snapshot="patient.b@example.com",
            specialty_snapshot="Dermatology",
            date=date.today() + timedelta(days=3),
            time_slot="14:00 - 14:30",
            status=AppointmentStatus.CONFIRMED,
            notes="Skin rash consultation"
        )

        # Appointment 3: Completed
        self.appt_completed = Appointment.objects.create(
            booked_by=self.patient_a,
            patient_profile=self.profile_a,
            doctor=self.doc_hosp,
            hospital=self.hospital,
            patient_name_snapshot="Alice Patient",
            patient_phone_snapshot="+971501111111",
            patient_email_snapshot="patient.a@example.com",
            specialty_snapshot="Cardiology",
            date=date.today() - timedelta(days=5),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.COMPLETED
        )

        # Appointment 4: Cancelled
        self.appt_cancelled = Appointment.objects.create(
            booked_by=self.patient_b,
            patient_profile=self.profile_b,
            doctor=self.doc_clinic,
            clinic=self.clinic,
            patient_name_snapshot="Bob Patient",
            patient_phone_snapshot="+971502222222",
            patient_email_snapshot="patient.b@example.com",
            specialty_snapshot="Dermatology",
            date=date.today() - timedelta(days=2),
            time_slot="15:00 - 15:30",
            status=AppointmentStatus.CANCELLED,
            cancel_reason="Rescheduled by patient"
        )

        self.list_url = reverse('admin_onboarding:admin_booking_list')

    # =========================================================================
    # AUTHORIZATION TESTS — GET /api/v1/admin/bookings/
    # =========================================================================

    def test_01_anonymous_cannot_list_bookings(self):
        """1. Anonymous requests to admin bookings are rejected with 401."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_02_patient_cannot_list_global_bookings(self):
        """2. Patient role cannot list platform-wide bookings (403)."""
        self.client.force_authenticate(user=self.patient_a)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_03_doctor_cannot_list_global_bookings(self):
        """3. Doctor role cannot list platform-wide bookings (403)."""
        self.client.force_authenticate(user=self.doc_hosp_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_04_facility_admin_cannot_list_global_bookings(self):
        """4. Hospital and Clinic facility admins cannot list global bookings (403)."""
        self.client.force_authenticate(user=self.hosp_admin)
        res_hosp = self.client.get(self.list_url)
        self.assertEqual(res_hosp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.clinic_admin)
        res_clinic = self.client.get(self.list_url)
        self.assertEqual(res_clinic.status_code, status.HTTP_403_FORBIDDEN)

    def test_05_platform_admin_can_list_global_bookings(self):
        """5. Platform superadmin can access platform-wide bookings (200)."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 4)

    def test_06_staff_user_can_list_global_bookings(self):
        """6. is_staff user is also authorized to view global bookings (200)."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 4)

    # =========================================================================
    # FUNCTIONAL TESTS — VISIBILITY, FILTERING & SEARCH
    # =========================================================================

    def test_07_bookings_across_facilities_are_visible(self):
        """7. Bookings across both hospitals and clinics are returned with facility details."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']
        booking_ids = [b['id'] for b in results]
        self.assertIn(str(self.appt_hosp.id), booking_ids)
        self.assertIn(str(self.appt_clinic.id), booking_ids)

        hosp_booking = next(b for b in results if b['id'] == str(self.appt_hosp.id))
        self.assertEqual(hosp_booking['patientName'], "Alice Patient")
        self.assertEqual(hosp_booking['doctorName'], "Dr. Zayd Mansoor")
        self.assertEqual(hosp_booking['facilityName'], "Oasis Specialty Hospital")
        self.assertEqual(hosp_booking['hospitalName'], "Oasis Specialty Hospital")
        self.assertEqual(hosp_booking['specialty'], "Cardiology")
        self.assertEqual(hosp_booking['status'], "confirmed")

        clinic_booking = next(b for b in results if b['id'] == str(self.appt_clinic.id))
        self.assertEqual(clinic_booking['patientName'], "Bob Patient")
        self.assertEqual(clinic_booking['doctorName'], "Dr. Layla Nour")
        self.assertEqual(clinic_booking['facilityName'], "Sunrise Family Clinic")
        self.assertEqual(clinic_booking['specialty'], "Dermatology")
        self.assertEqual(clinic_booking['status'], "confirmed")

    def test_08_pagination_works_correctly(self):
        """8. Bookings pagination supports page & page_size envelope."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.list_url}?page=1&page_size=2")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 4)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])

    def test_09_status_filter_works(self):
        """9. Status filter (?status=confirmed / completed / cancelled) isolates records."""
        self.client.force_authenticate(user=self.admin_user)

        res_conf = self.client.get(f"{self.list_url}?status=confirmed")
        self.assertEqual(res_conf.data['count'], 2)

        res_comp = self.client.get(f"{self.list_url}?status=completed")
        self.assertEqual(res_comp.data['count'], 1)
        self.assertEqual(res_comp.data['results'][0]['id'], str(self.appt_completed.id))

        res_canc = self.client.get(f"{self.list_url}?status=cancelled")
        self.assertEqual(res_canc.data['count'], 1)
        self.assertEqual(res_canc.data['results'][0]['id'], str(self.appt_cancelled.id))

    def test_10_search_filter_works(self):
        """10. Search query parameter filters by patient name, doctor, or facility."""
        self.client.force_authenticate(user=self.admin_user)

        # Search by patient name
        res_pat = self.client.get(f"{self.list_url}?search=Alice")
        self.assertEqual(res_pat.data['count'], 2)

        # Search by doctor name
        res_doc = self.client.get(f"{self.list_url}?search=Layla")
        self.assertEqual(res_doc.data['count'], 2)

        # Search by facility name
        res_fac = self.client.get(f"{self.list_url}?search=Oasis")
        self.assertEqual(res_fac.data['count'], 2)

        # Search by exact booking UUID
        res_uuid = self.client.get(f"{self.list_url}?search={self.appt_clinic.id}")
        self.assertEqual(res_uuid.data['count'], 1)
        self.assertEqual(res_uuid.data['results'][0]['id'], str(self.appt_clinic.id))

    # =========================================================================
    # CANCELLATION TESTS — POST /api/v1/admin/bookings/<id>/cancel/
    # =========================================================================

    def test_11_platform_admin_can_cancel_eligible_appointment(self):
        """11. Platform admin can cancel a confirmed appointment with reason."""
        self.client.force_authenticate(user=self.admin_user)
        cancel_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': self.appt_hosp.id})

        response = self.client.post(cancel_url, {'reason': 'Doctor emergency leave'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'cancelled')
        self.assertEqual(response.data['cancelReason'], 'Doctor emergency leave')

        self.appt_hosp.refresh_from_db()
        self.assertEqual(self.appt_hosp.status, AppointmentStatus.CANCELLED)
        self.assertEqual(self.appt_hosp.cancel_reason, 'Doctor emergency leave')
        self.assertEqual(self.appt_hosp.cancelled_by_role, UserRole.ADMIN)
        self.assertEqual(self.appt_hosp.cancelled_by_user, self.admin_user)

    def test_12_cancellation_preserves_notifications(self):
        """12. Cancellation dispatches in-app notifications to patient and doctor."""
        self.client.force_authenticate(user=self.admin_user)
        cancel_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': self.appt_hosp.id})

        Notification.objects.all().delete()
        self.client.post(cancel_url, {'reason': 'Hospital renovation'}, format='json')

        # Patient notification
        pat_notif = Notification.objects.filter(user=self.patient_a).first()
        self.assertIsNotNone(pat_notif)
        self.assertIn("cancelled", pat_notif.title.lower())

        # Doctor notification
        doc_notif = Notification.objects.filter(user=self.doc_hosp_user).first()
        self.assertIsNotNone(doc_notif)
        self.assertIn("cancelled", doc_notif.title.lower())

    def test_13_cannot_cancel_already_cancelled_appointment(self):
        """13. Attempting to cancel an already cancelled appointment returns 400."""
        self.client.force_authenticate(user=self.admin_user)
        cancel_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': self.appt_cancelled.id})

        response = self.client.post(cancel_url, {'reason': 'Duplicate cancel'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'ALREADY_CANCELLED')

    def test_14_cannot_cancel_completed_appointment(self):
        """14. State machine forbids cancelling an already completed consultation (400)."""
        self.client.force_authenticate(user=self.admin_user)
        cancel_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': self.appt_completed.id})

        response = self.client.post(cancel_url, {'reason': 'Post-consult cancel'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'CANNOT_CANCEL_COMPLETED')

    def test_15_non_admin_cannot_cancel_via_admin_endpoint(self):
        """15. Non-admin roles (anonymous, patient, doctor, facility admin) are rejected."""
        cancel_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': self.appt_hosp.id})

        # Anonymous -> 401
        res_anon = self.client.post(cancel_url, {'reason': 'Cancel'}, format='json')
        self.assertEqual(res_anon.status_code, status.HTTP_401_UNAUTHORIZED)

        # Patient -> 403
        self.client.force_authenticate(user=self.patient_a)
        res_pat = self.client.post(cancel_url, {'reason': 'Cancel'}, format='json')
        self.assertEqual(res_pat.status_code, status.HTTP_403_FORBIDDEN)

        # Doctor -> 403
        self.client.force_authenticate(user=self.doc_hosp_user)
        res_doc = self.client.post(cancel_url, {'reason': 'Cancel'}, format='json')
        self.assertEqual(res_doc.status_code, status.HTTP_403_FORBIDDEN)

        # Facility Admin -> 403
        self.client.force_authenticate(user=self.hosp_admin)
        res_hosp = self.client.post(cancel_url, {'reason': 'Cancel'}, format='json')
        self.assertEqual(res_hosp.status_code, status.HTTP_403_FORBIDDEN)

    def test_16_nonexistent_appointment_returns_404(self):
        """16. Nonexistent appointment UUID returns 404 Not Found."""
        self.client.force_authenticate(user=self.admin_user)
        fake_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': uuid.uuid4()})
        response = self.client.post(fake_url, {'reason': 'Cancel non-existing'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_17_audit_event_logged_on_administrative_cancellation(self):
        """17. Immutable audit log is recorded on admin cancellation without PHI."""
        self.client.force_authenticate(user=self.admin_user)
        cancel_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': self.appt_clinic.id})

        self.client.post(cancel_url, {'reason': 'Clinic schedule change'}, format='json')

        audit_entry = AuditLog.objects.filter(
            action="APPOINTMENT_CANCELLED",
            target_model="Appointment",
            target_id=str(self.appt_clinic.id)
        ).first()

        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.actor, self.admin_user)
        self.assertEqual(audit_entry.change_summary.get('previous_status'), 'confirmed')
        self.assertEqual(audit_entry.change_summary.get('new_status'), 'cancelled')
        self.assertEqual(audit_entry.change_summary.get('reason'), 'Clinic schedule change')

        # PHI / sensitive credential minimization check
        summary_str = str(audit_entry.change_summary).lower()
        for forbidden in ['password', 'token', 'secret', 'diagnosis', 'prescription']:
            self.assertNotIn(forbidden, summary_str)

    def test_18_arbitrary_field_tampering_prevented_on_cancel(self):
        """18. Cancellation endpoint rejects mutation of patient, doctor, date, or notes."""
        self.client.force_authenticate(user=self.admin_user)
        cancel_url = reverse('admin_onboarding:admin_booking_cancel', kwargs={'pk': self.appt_hosp.id})

        payload = {
            'reason': 'Administrative cancellation',
            'notes': 'Hacked clinical notes',
            'patient_name_snapshot': 'Attacker Name',
            'doctor_id': str(uuid.uuid4()),
            'status': 'completed',
        }
        response = self.client.post(cancel_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.appt_hosp.refresh_from_db()
        self.assertEqual(self.appt_hosp.status, AppointmentStatus.CANCELLED)
        self.assertEqual(self.appt_hosp.notes, "Routine heart check")
        self.assertEqual(self.appt_hosp.patient_name_snapshot, "Alice Patient")
        self.assertEqual(self.appt_hosp.doctor, self.doc_hosp)

    def test_19_no_sensitive_or_clinical_fields_leaked_in_bookings_response(self):
        """19. Bookings list response does not leak credentials or unneeded clinical data."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        resp_str = str(response.data).lower()
        for forbidden in ['password', 'token', 'secret', 'hash', 'ssn', 'diagnosis', 'prescription']:
            self.assertNotIn(forbidden, resp_str)
