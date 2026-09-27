"""Automated Test Suite for Phase 5 Appointment Booking & Management Workflows."""
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole, PatientProfile, PatientDependent
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus
from apps.audit.models import AuditLog

class AppointmentWorkflowTests(TestCase):
    """Test suite covering Phase 5 appointment booking, authorization, and management."""

    def setUp(self):
        self.client = APIClient()

        # 1. Medical Facilities
        self.active_hospital = Hospital.objects.create(
            name="American Hospital Dubai",
            location="Oud Metha, Dubai",
            address="19th St, Oud Metha",
            phone="+97143775500",
            operating_hours="24/7",
            about="Accredited hospital.",
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
        self.hospital_b = Hospital.objects.create(
            name="City Care Hospital",
            location="Al Barsha, Dubai",
            address="Al Barsha St",
            phone="+97143000000",
            operating_hours="24/7",
            about="Hospital B facility.",
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
        self.deactivated_hospital = Hospital.objects.create(
            name="Old Closed Hospital",
            location="Deira",
            address="Deira St",
            phone="+97140000000",
            status=FacilityStatus.DEACTIVATED
        )
        self.active_clinic = Clinic.objects.create(
            name="Prime Dental Care Clinic",
            location="Jumeirah, Dubai",
            address="Jumeirah Beach Road",
            primary_specialty="Dental",
            phone="+97143441122",
            operating_hours="09:00 - 20:00",
            about="Dental clinic.",
            status=FacilityStatus.ACTIVE
        )

        # 2. Facility Administrators
        self.hosp_admin_user = User.objects.create_user(
            email="admin.american@example.com",
            name="American Hospital Admin",
            password="StrongPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.active_hospital.admin_user = self.hosp_admin_user
        self.active_hospital.save()

        self.hosp_b_admin_user = User.objects.create_user(
            email="admin.citycare@example.com",
            name="City Care Admin",
            password="StrongPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.hospital_b.admin_user = self.hosp_b_admin_user
        self.hospital_b.save()

        self.clinic_admin_user = User.objects.create_user(
            email="admin.prime@example.com",
            name="Prime Clinic Admin",
            password="StrongPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.active_clinic.admin_user = self.clinic_admin_user
        self.active_clinic.save()

        # 3. Doctors
        # Doctor A @ Active Hospital
        self.doctor_a_user = User.objects.create_user(
            email="doc.jenkins@example.com",
            name="Dr. Sarah Jenkins",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doctor_a = Doctor.objects.create(
            user=self.doctor_a_user,
            name="Dr. Sarah Jenkins",
            hospital=self.active_hospital,
            specialty="Cardiology",
            location="Oud Metha, Dubai",
            consultation_fee=400.00,
            status=FacilityStatus.ACTIVE
        )
        self.schedule_a = DoctorSchedule.objects.create(
            doctor=self.doctor_a,
            available_days=["Monday", "Wednesday"],
            standard_slots=["09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM"],
            slot_duration_minutes=30
        )

        # Doctor B @ Hospital B
        self.doctor_b_user = User.objects.create_user(
            email="doc.mansoor@example.com",
            name="Dr. Tariq Al-Mansoor",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doctor_b = Doctor.objects.create(
            user=self.doctor_b_user,
            name="Dr. Tariq Al-Mansoor",
            hospital=self.hospital_b,
            specialty="Neurology",
            location="Al Barsha, Dubai",
            status=FacilityStatus.ACTIVE
        )
        self.schedule_b = DoctorSchedule.objects.create(
            doctor=self.doctor_b,
            available_days=["Monday"],
            standard_slots=["10:00 AM", "10:30 AM"],
            slot_duration_minutes=30
        )

        # Doctor C @ Active Clinic
        self.doctor_c_user = User.objects.create_user(
            email="doc.zaid@example.com",
            name="Dr. Kareem Zaid",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doctor_c = Doctor.objects.create(
            user=self.doctor_c_user,
            name="Dr. Kareem Zaid",
            clinic=self.active_clinic,
            specialty="Dental",
            location="Jumeirah",
            status=FacilityStatus.ACTIVE
        )
        self.schedule_c = DoctorSchedule.objects.create(
            doctor=self.doctor_c,
            available_days=["Monday"],
            standard_slots=["02:00 PM", "02:30 PM"]
        )

        # Doctor D (Inactive)
        self.doctor_d = Doctor.objects.create(
            name="Dr. Deactivated",
            hospital=self.active_hospital,
            specialty="Cardiology",
            status=FacilityStatus.DEACTIVATED
        )

        # Doctor E @ Deactivated Hospital
        self.doctor_e = Doctor.objects.create(
            name="Dr. Inactive Hospital Doc",
            hospital=self.deactivated_hospital,
            specialty="Cardiology",
            status=FacilityStatus.ACTIVE
        )

        # 4. Patients
        # Patient 1
        self.patient_1 = User.objects.create_user(
            email="patient1@example.com",
            name="Patient One",
            password="StrongPassword2026!",
            role=UserRole.PATIENT,
            phone="+971501112233"
        )
        self.patient_1_profile = PatientProfile.objects.create(user=self.patient_1)
        self.dep_1 = PatientDependent.objects.create(
            profile=self.patient_1_profile,
            name="Little Patient One",
            relation="Child",
            dob=date(2018, 5, 10),
            gender="Female",
            emergency_contact="+971501112233"
        )

        # Patient 2
        self.patient_2 = User.objects.create_user(
            email="patient2@example.com",
            name="Patient Two",
            password="StrongPassword2026!",
            role=UserRole.PATIENT,
            phone="+971509998877"
        )
        self.patient_2_profile = PatientProfile.objects.create(user=self.patient_2)
        self.dep_2 = PatientDependent.objects.create(
            profile=self.patient_2_profile,
            name="Little Patient Two",
            relation="Child",
            dob=date(2019, 3, 15),
            gender="Male"
        )

        # Future booking date: target next Monday
        today = date.today()
        days_ahead = (0 - today.weekday()) % 7  # 0 is Monday
        if days_ahead <= 0:
            days_ahead += 7
        self.future_monday = today + timedelta(days=days_ahead)
        # Next Tuesday (Doctor A does NOT practice on Tuesdays)
        self.future_tuesday = self.future_monday + timedelta(days=1)

    # -------------------------------------------------------------------------
    # 1. BOOKING ENGINE TESTS
    # -------------------------------------------------------------------------

    def test_authenticated_patient_can_book_successfully(self):
        """Test 1: Authenticated patient books appointment for self."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        payload = {
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_monday),
            "time_slot": "09:00 AM",
            "notes": "Annual heart check-up"
        }

        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['patientName'], "Patient One")
        self.assertEqual(res.data['doctorName'], "Dr. Sarah Jenkins")
        self.assertEqual(res.data['status'], "confirmed")
        self.assertEqual(res.data['timeSlot'], "09:00 AM")
        self.assertEqual(res.data['providerName'], "American Hospital Dubai")

        # Verify database record
        apt = Appointment.objects.get(id=res.data['id'])
        self.assertEqual(apt.booked_by, self.patient_1)
        self.assertEqual(apt.patient_profile, self.patient_1_profile)
        self.assertIsNone(apt.dependent)
        self.assertEqual(apt.specialty_snapshot, "Cardiology")

    def test_unauthenticated_user_cannot_book(self):
        """Test 2: Unauthenticated booking attempts are rejected with 401."""
        url = reverse('appointments:appointment_booking')
        payload = {
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_monday),
            "time_slot": "09:00 AM"
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patient_cannot_impersonate_another_patient(self):
        """Test 3: Backend derives booked_by strictly from request.user, ignoring body patientId."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        # Malicious payload trying to impersonate Patient 2
        payload = {
            "patientId": str(self.patient_2.id),
            "patient_id": str(self.patient_2.id),
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_monday),
            "time_slot": "09:00 AM"
        }

        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        apt = Appointment.objects.get(id=res.data['id'])
        # Must belong to Patient 1, NOT Patient 2
        self.assertEqual(apt.booked_by, self.patient_1)
        self.assertEqual(apt.patient_profile, self.patient_1_profile)
        self.assertEqual(apt.patient_name_snapshot, "Patient One")

    def test_patient_can_book_authorized_dependent(self):
        """Test 4: Patient books appointment for their own authorized dependent."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        payload = {
            "doctor_id": str(self.doctor_a.id),
            "dependent_id": str(self.dep_1.id),
            "date": str(self.future_monday),
            "time_slot": "09:30 AM",
            "notes": "Pediatric consultation"
        }

        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['patientName'], "Little Patient One")
        self.assertTrue(res.data['is_dependent'])
        self.assertEqual(res.data['dependent_id'], str(self.dep_1.id))

        apt = Appointment.objects.get(id=res.data['id'])
        self.assertEqual(apt.booked_by, self.patient_1)
        self.assertIsNone(apt.patient_profile)
        self.assertEqual(apt.dependent, self.dep_1)

    def test_patient_cannot_book_another_patients_dependent(self):
        """Test 5: Cross-account dependent booking is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        # Patient 1 tries to book for Patient 2's dependent
        payload = {
            "doctor_id": str(self.doctor_a.id),
            "dependent_id": str(self.dep_2.id),
            "date": str(self.future_monday),
            "time_slot": "09:00 AM"
        }

        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.data['code'], "DEPENDENT_NOT_FOUND")

    def test_inactive_doctor_cannot_be_booked(self):
        """Test 6: Booking an inactive doctor returns 404."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        payload = {
            "doctor_id": str(self.doctor_d.id),
            "date": str(self.future_monday),
            "time_slot": "09:00 AM"
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_at_inactive_facility_cannot_be_booked(self):
        """Test 7: Booking a doctor whose affiliated facility is inactive is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        payload = {
            "doctor_id": str(self.doctor_e.id),
            "date": str(self.future_monday),
            "time_slot": "09:00 AM"
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['code'], "INACTIVE_FACILITY")

    def test_invalid_slot_rejected(self):
        """Test 8: Slot not configured in doctor standard_slots is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        payload = {
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_monday),
            "time_slot": "03:15 AM"  # Invalid slot
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['code'], "INVALID_SLOT")

    def test_unavailable_day_rejected(self):
        """Test 9: Date on which doctor does not practice is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        payload = {
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_tuesday),  # Tuesday (Doctor A only practices Mon/Wed)
            "time_slot": "09:00 AM"
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['code'], "DOCTOR_UNAVAILABLE")

    def test_duplicate_active_booking_rejected_with_409(self):
        """Test 10 & 13: Second attempt to book already-taken slot returns 409 SLOT_ALREADY_BOOKED."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        payload = {
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_monday),
            "time_slot": "10:00 AM"
        }

        # First booking succeeds
        res1 = self.client.post(url, payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Second booking by Patient 2 for exact same doctor, date, slot -> 409 Conflict
        self.client.force_authenticate(user=self.patient_2)
        res2 = self.client.post(url, payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res2.data['code'], "SLOT_ALREADY_BOOKED")

    # -------------------------------------------------------------------------
    # 2. PATIENT APPOINTMENTS & OBJECT ISOLATION TESTS
    # -------------------------------------------------------------------------

    def test_patient_sees_only_own_appointments(self):
        """Test 14 & 15: Patient list and detail endpoints strictly isolate patient data."""
        # Patient 1 creates appointment
        apt1 = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.patient_1_profile,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=self.future_monday,
            time_slot="09:00 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient One"
        )
        # Patient 2 creates appointment
        apt2 = Appointment.objects.create(
            booked_by=self.patient_2,
            patient_profile=self.patient_2_profile,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=self.future_monday,
            time_slot="09:30 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient Two"
        )

        # Patient 1 lists appointments
        self.client.force_authenticate(user=self.patient_1)
        res_list = self.client.get(reverse('appointments:my_appointments'))
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        appt_ids = [a['id'] for a in res_list.data]
        self.assertIn(str(apt1.id), appt_ids)
        self.assertNotIn(str(apt2.id), appt_ids)

        # Patient 1 can view own appointment detail
        res_detail = self.client.get(reverse('appointments:appointment_detail', kwargs={'pk': apt1.id}))
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # Patient 1 tries to view Patient 2's appointment -> 404 (IDOR prevented)
        res_idor = self.client.get(reverse('appointments:appointment_detail', kwargs={'pk': apt2.id}))
        self.assertEqual(res_idor.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # 3. DOCTOR APPOINTMENTS & STATUS TRANSITIONS
    # -------------------------------------------------------------------------

    def test_doctor_sees_only_own_appointments(self):
        """Test 16 & 17: Doctor can inspect only their own consultations."""
        apt_doc_a = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.patient_1_profile,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=self.future_monday,
            time_slot="09:00 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient One"
        )
        apt_doc_b = Appointment.objects.create(
            booked_by=self.patient_2,
            patient_profile=self.patient_2_profile,
            doctor=self.doctor_b,
            hospital=self.hospital_b,
            date=self.future_monday,
            time_slot="10:00 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient Two"
        )

        # Doctor A lists appointments
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.get(reverse('appointments:doctor_appointments'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        appt_ids = [a['id'] for a in res.data]
        self.assertIn(str(apt_doc_a.id), appt_ids)
        self.assertNotIn(str(apt_doc_b.id), appt_ids)

        # Doctor A tries to access Doctor B's appointment detail -> 404
        res_b = self.client.get(reverse('appointments:appointment_detail', kwargs={'pk': apt_doc_b.id}))
        self.assertEqual(res_b.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_authorized_status_transition(self):
        """Test 24: Doctor marks confirmed consultation as completed."""
        apt = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.patient_1_profile,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=self.future_monday,
            time_slot="09:00 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient One"
        )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('appointments:doctor_appointment_status', kwargs={'pk': apt.id})

        res = self.client.patch(url, {"status": "completed"}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], "completed")

        apt.refresh_from_db()
        self.assertEqual(apt.status, AppointmentStatus.COMPLETED)

    def test_invalid_status_transition_rejected(self):
        """Test 23: Attempting invalid status transition is rejected with 400."""
        # Completed appointment cannot be cancelled
        completed_apt = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.patient_1_profile,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=self.future_monday,
            time_slot="09:00 AM",
            status=AppointmentStatus.COMPLETED,
            patient_name_snapshot="Patient One"
        )

        self.client.force_authenticate(user=self.patient_1)
        res_cancel = self.client.post(
            reverse('appointments:appointment_cancel', kwargs={'pk': completed_apt.id}),
            {"reason": "Want to cancel"},
            format='json'
        )
        self.assertEqual(res_cancel.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_cancel.data['code'], "CANNOT_CANCEL_COMPLETED")

    # -------------------------------------------------------------------------
    # 4. HOSPITAL & CLINIC FACILITY ISOLATION & CANCELLATION
    # -------------------------------------------------------------------------

    def test_facility_admin_isolation_and_cancellation(self):
        """Test 18, 19, 20, 21, 22: Facility isolation and administrative emergency cancellation."""
        apt_hosp_a = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.patient_1_profile,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=self.future_monday,
            time_slot="09:00 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient One"
        )
        apt_hosp_b = Appointment.objects.create(
            booked_by=self.patient_2,
            patient_profile=self.patient_2_profile,
            doctor=self.doctor_b,
            hospital=self.hospital_b,
            date=self.future_monday,
            time_slot="10:00 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient Two"
        )

        # Hospital A Admin lists appointments
        self.client.force_authenticate(user=self.hosp_admin_user)
        res_list = self.client.get(reverse('appointments:hospital_appointments'))
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        ids = [a['id'] for a in res_list.data]
        self.assertIn(str(apt_hosp_a.id), ids)
        self.assertNotIn(str(apt_hosp_b.id), ids)

        # Hospital A Admin cancels appointment at Hospital A -> Success
        cancel_url = reverse('hospital_admin_appointments:hospital_admin_cancel', kwargs={'pk': apt_hosp_a.id})
        res_cancel = self.client.post(cancel_url, {"reason": "Doctor called in sick"}, format='json')
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cancel.data['status'], "cancelled")
        self.assertEqual(res_cancel.data['cancelReason'], "Doctor called in sick")
        self.assertEqual(res_cancel.data['cancelledBy'], "hospital")

        # Hospital A Admin tries to cancel Hospital B's appointment -> 404 (IDOR rejected)
        cancel_b_url = reverse('hospital_admin_appointments:hospital_admin_cancel', kwargs={'pk': apt_hosp_b.id})
        res_cancel_b = self.client.post(cancel_b_url, {"reason": "Malicious attempt"}, format='json')
        self.assertEqual(res_cancel_b.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # 5. AUDIT LOGGING & CLINICAL ACCESS TESTS
    # -------------------------------------------------------------------------

    def test_audit_event_creation(self):
        """Test 25: Critical appointment actions create immutable sanitized audit log records."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')

        res = self.client.post(url, {
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_monday),
            "time_slot": "10:30 AM"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        apt_id = res.data['id']

        # Verify APPOINTMENT_CREATED audit log exists
        log_create = AuditLog.objects.filter(
            action="APPOINTMENT_CREATED",
            target_id=str(apt_id)
        ).first()
        self.assertIsNotNone(log_create)
        self.assertEqual(log_create.actor, self.patient_1)
        self.assertEqual(log_create.change_summary['time_slot'], "10:30 AM")

        # Now cancel the appointment
        self.client.post(
            reverse('appointments:appointment_cancel', kwargs={'pk': apt_id}),
            {"reason": "Changed schedule"},
            format='json'
        )

        log_cancel = AuditLog.objects.filter(
            action="APPOINTMENT_CANCELLED",
            target_id=str(apt_id)
        ).first()
        self.assertIsNotNone(log_cancel)
        self.assertEqual(log_cancel.actor, self.patient_1)
        self.assertEqual(log_cancel.change_summary['reason'], "Changed schedule")

    def test_clinical_relationship_remains_enforced(self):
        """Test 26: Confirmed appointment grants attending doctor clinical profile access."""
        # Before appointment: Doctor A cannot access Patient 1's medical profile
        self.client.force_authenticate(user=self.doctor_a_user)
        profile_url = reverse('doctors:doctor_patient_profile', kwargs={'patient_id': self.patient_1_profile.id})
        res_before = self.client.get(profile_url)
        self.assertEqual(res_before.status_code, status.HTTP_404_NOT_FOUND)

        # Create confirmed appointment between Doctor A and Patient 1
        Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.patient_1_profile,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=self.future_monday,
            time_slot="09:00 AM",
            status=AppointmentStatus.CONFIRMED,
            patient_name_snapshot="Patient One"
        )

        # Now Doctor A can access medical profile
        res_after = self.client.get(profile_url)
        self.assertEqual(res_after.status_code, status.HTTP_200_OK)

    @patch('apps.appointments.views.Appointment.objects.create')
    def test_unrelated_integrity_error_is_reraised(self, mock_create):
        """
        Regression Test: Verify that an unrelated IntegrityError (e.g. check constraint,
        foreign key failure) is NOT converted to 409 SLOT_ALREADY_BOOKED and is re-raised.
        """
        from django.db import IntegrityError
        # Simulate an unrelated foreign key or check constraint failure
        mock_create.side_effect = IntegrityError("FOREIGN KEY constraint failed: unrelated_table.user_id")

        self.client.force_authenticate(user=self.patient_1)
        url = reverse('appointments:appointment_booking')
        payload = {
            "doctor_id": str(self.doctor_a.id),
            "date": str(self.future_monday),
            "time_slot": "09:00 AM",
            "notes": "Testing unrelated error handling"
        }
        with self.assertRaises(IntegrityError):
            self.client.post(url, payload, format='json')
