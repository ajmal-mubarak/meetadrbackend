"""Comprehensive Automated Test Suite for Phase 9: Doctor Portal Operations, Schedule & Patient Directory."""
import uuid
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole, PatientProfile, PatientDependent, RelationType
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus
from apps.audit.models import AuditLog


class DoctorPortalTests(TestCase):
    """Test suite covering Doctor Schedule, Dashboard KPIs, and Patient Directory."""

    def setUp(self):
        self.client = APIClient()

        # 1. Hospital & Attending Doctor A
        self.hospital = Hospital.objects.create(
            name="American Hospital Dubai",
            location="Oud Metha, Dubai",
            address="19th St, Oud Metha",
            phone="+97143775500",
            operating_hours="24/7",
            status=FacilityStatus.ACTIVE
        )

        self.doctor_a_user = User.objects.create_user(
            email="dr.a@americanhospital.ae",
            role=UserRole.DOCTOR,
            phone="+971501112233",
            name="Dr. Tariq Al-Mansoor"
        )
        self.doctor_a = Doctor.objects.create(
            user=self.doctor_a_user,
            hospital=self.hospital,
            name="Dr. Tariq Al-Mansoor",
            specialty="Cardiology",
            experience_years=14,
            consultation_fee=Decimal("400.00"),
            rating=Decimal("4.90"),
            review_count=20,
            status=FacilityStatus.ACTIVE
        )

        # 2. Doctor B (distinct doctor for isolation testing)
        self.doctor_b_user = User.objects.create_user(
            email="dr.b@americanhospital.ae",
            role=UserRole.DOCTOR,
            phone="+971509998877",
            name="Dr. Sarah Jones"
        )
        self.doctor_b = Doctor.objects.create(
            user=self.doctor_b_user,
            hospital=self.hospital,
            name="Dr. Sarah Jones",
            specialty="Neurology",
            consultation_fee=Decimal("500.00"),
            rating=Decimal("4.75"),
            review_count=12,
            status=FacilityStatus.ACTIVE
        )

        # 3. Patients (Primary & Dependents)
        self.patient_1_user = User.objects.create_user(
            email="patient.one@example.com",
            role=UserRole.PATIENT,
            phone="+971501110001",
            name="Alice Patient"
        )
        self.patient_1_profile = PatientProfile.objects.create(
            user=self.patient_1_user,
            gender="Female",
            blood_group="O+"
        )
        self.dependent_child = PatientDependent.objects.create(
            profile=self.patient_1_profile,
            name="Tommy Patient",
            relation=RelationType.CHILD,
            gender="Male",
            blood_group="O+"
        )

        self.patient_2_user = User.objects.create_user(
            email="patient.two@example.com",
            role=UserRole.PATIENT,
            phone="+971502220002",
            name="Bob Walker"
        )
        self.patient_2_profile = PatientProfile.objects.create(
            user=self.patient_2_user,
            gender="Male",
            blood_group="A+"
        )

        # 4. Admins
        self.hospital_admin_user = User.objects.create_user(
            email="hosp.admin@americanhospital.ae",
            role=UserRole.HOSPITAL,
            phone="+971503334455",
            name="Hospital Admin"
        )
        self.hospital.admin = self.hospital_admin_user
        self.hospital.save()

        self.platform_admin_user = User.objects.create_user(
            email="superadmin@meetadr.com",
            role=UserRole.ADMIN,
            phone="+971505556677",
            name="Platform Superadmin",
            is_staff=True
        )

    # =========================================================================
    # A. Schedule API Tests
    # =========================================================================

    def test_01_doctor_get_own_schedule_auto_provision(self):
        """1. Doctor GET schedule auto-creates default schedule if missing."""
        self.assertFalse(DoctorSchedule.objects.filter(doctor=self.doctor_a).exists())

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(DoctorSchedule.objects.filter(doctor=self.doctor_a).exists())
        self.assertIn('Monday', response.data['available_days'])
        self.assertIn('09:00 - 09:30', response.data['standard_slots'])
        self.assertEqual(response.data['slot_duration_minutes'], 30)
        # Check camelCase aliases
        self.assertEqual(response.data['availableDays'], response.data['available_days'])
        self.assertEqual(response.data['standardSlots'], response.data['standard_slots'])
        self.assertEqual(response.data['slotDurationMinutes'], 30)

    def test_02_repeated_get_does_not_duplicate_schedule(self):
        """2. Repeated GET calls do not create duplicate schedule rows."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(DoctorSchedule.objects.filter(doctor=self.doctor_a).count(), 1)

    def test_03_doctor_put_schedule(self):
        """3. Doctor PUT completely replaces schedule."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        payload = {
            'available_days': ['Sunday', 'Tuesday', 'Thursday'],
            'standard_slots': ['10:00 - 10:30', '10:30 - 11:00'],
            'slot_duration_minutes': 30
        }
        res = self.client.put(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['available_days'], ['Sunday', 'Tuesday', 'Thursday'])
        self.assertEqual(res.data['standard_slots'], ['10:00 - 10:30', '10:30 - 11:00'])

        # Verify database record
        sched = DoctorSchedule.objects.get(doctor=self.doctor_a)
        self.assertEqual(sched.available_days, ['Sunday', 'Tuesday', 'Thursday'])

        # Verify audit log
        log = AuditLog.objects.filter(action='DOCTOR_SCHEDULE_UPDATED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.doctor_a_user)
        self.assertEqual(log.change_summary['doctor_id'], str(self.doctor_a.id))
        self.assertEqual(log.change_summary['available_days_count'], 3)
        self.assertEqual(log.change_summary['standard_slots_count'], 2)

    def test_04_doctor_patch_schedule(self):
        """4. Doctor PATCH updates only specified fields."""
        # Provision default
        DoctorSchedule.objects.create(
            doctor=self.doctor_a,
            available_days=['Monday', 'Tuesday'],
            standard_slots=['09:00 - 09:30'],
            slot_duration_minutes=30
        )
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        res = self.client.patch(url, {'availableDays': ['Wednesday', 'Thursday']}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['available_days'], ['Wednesday', 'Thursday'])
        # standard_slots preserved
        self.assertEqual(res.data['standard_slots'], ['09:00 - 09:30'])

    def test_05_invalid_weekday_rejected(self):
        """5. Invalid weekday (e.g. 'Funday') -> 400 Bad Request."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        res = self.client.put(url, {'available_days': ['Monday', 'Funday']}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_06_malformed_slots_rejected(self):
        """6. Malformed empty or non-string slot -> 400."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        res = self.client.put(url, {'standard_slots': ['']}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_07_excessive_slots_rejected(self):
        """7. Excessive slot count (> 50) -> 400."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        too_many_slots = [f"Slot {i}" for i in range(51)]
        res = self.client.put(url, {'standard_slots': too_many_slots}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_08_invalid_slot_duration_rejected(self):
        """8. Invalid slot duration (< 10 or > 120) -> 400."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        res = self.client.patch(url, {'slot_duration_minutes': 5}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res2 = self.client.patch(url, {'slot_duration_minutes': 180}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_09_schedule_auth_permissions(self):
        """9. Unauthenticated -> 401; Patient/Admin -> 403."""
        url = reverse('doctors:doctor_schedule')

        # 401 unauthenticated
        res_unauth = self.client.get(url)
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # 403 patient
        self.client.force_authenticate(user=self.patient_1_user)
        res_pat = self.client.get(url)
        self.assertEqual(res_pat.status_code, status.HTTP_403_FORBIDDEN)

        # 403 hospital admin
        self.client.force_authenticate(user=self.hospital_admin_user)
        res_hosp = self.client.get(url)
        self.assertEqual(res_hosp.status_code, status.HTTP_403_FORBIDDEN)

        # 403 platform admin
        self.client.force_authenticate(user=self.platform_admin_user)
        res_adm = self.client.get(url)
        self.assertEqual(res_adm.status_code, status.HTTP_403_FORBIDDEN)

    def test_10_doctor_schedule_isolation(self):
        """10. Doctor A cannot read or modify Doctor B schedule (server derives doctor)."""
        DoctorSchedule.objects.create(
            doctor=self.doctor_b,
            available_days=['Friday', 'Saturday'],
            standard_slots=['14:00 - 14:30']
        )
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        # Even if doctor A passes a doctor_id query param or body, it must be ignored
        res = self.client.get(f"{url}?doctor_id={self.doctor_b.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Returns doctor A's schedule (auto-provisioned Monday-Friday), NOT doctor B's
        self.assertIn('Monday', res.data['available_days'])
        self.assertNotIn('Saturday', res.data['available_days'])

    # =========================================================================
    # B. Doctor Dashboard Tests
    # =========================================================================

    def test_11_dashboard_empty_state_zero_appointments(self):
        """11. Dashboard returns 0.0 completion rate and 0 revenue when no appointments exist."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_dashboard')
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        stats = res.data['stats']
        self.assertEqual(stats['totalAppointments'], 0)
        self.assertEqual(stats['todayAppointments'], 0)
        self.assertEqual(stats['completedAppointments'], 0)
        self.assertEqual(stats['completionRate'], 0.0)
        self.assertEqual(stats['totalRevenue'], 0.0)
        self.assertEqual(stats['activePatients'], 0)
        self.assertEqual(stats['rating'], 4.90)
        self.assertEqual(stats['reviewCount'], 20)
        self.assertEqual(len(res.data['weeklyTrend']), 7)
        self.assertEqual(len(res.data['upcomingAppointments']), 0)

    def test_12_dashboard_kpis_and_aggregations(self):
        """12. Dashboard correctly aggregates counts, completion rate, and gross revenue."""
        today = date.today()
        # Appointment 1: Completed today -> revenue 400
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_1_user,
            patient_profile=self.patient_1_profile,
            hospital=self.hospital,
            date=today,
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED
        )
        # Appointment 2: Completed yesterday -> revenue 400
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_1_user,
            patient_profile=self.patient_1_profile,
            hospital=self.hospital,
            date=today - timedelta(days=1),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.COMPLETED
        )
        # Appointment 3: Cancelled today -> NOT in revenue
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_2_user,
            patient_profile=self.patient_2_profile,
            hospital=self.hospital,
            date=today,
            time_slot="11:00 - 11:30",
            status=AppointmentStatus.CANCELLED
        )
        # Appointment 4: Confirmed tomorrow -> upcoming, NOT in revenue
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_2_user,
            patient_profile=self.patient_2_profile,
            hospital=self.hospital,
            date=today + timedelta(days=1),
            time_slot="14:00 - 14:30",
            status=AppointmentStatus.CONFIRMED,
            notes="Follow up review"
        )
        # Appointment 5 for Doctor B -> must NOT affect Doctor A
        Appointment.objects.create(
            doctor=self.doctor_b,
            booked_by=self.patient_2_user,
            patient_profile=self.patient_2_profile,
            hospital=self.hospital,
            date=today,
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED
        )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_dashboard')
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        stats = res.data['stats']

        # Total = 4 appointments for Doctor A
        self.assertEqual(stats['totalAppointments'], 4)
        # Today = Appt 1 (completed) + Appt 3 (cancelled) = 2
        self.assertEqual(stats['todayAppointments'], 2)
        # Completed = 2
        self.assertEqual(stats['completedAppointments'], 2)
        # Cancelled = 1
        self.assertEqual(stats['cancelledAppointments'], 1)
        # Confirmed = 1
        self.assertEqual(stats['confirmedAppointments'], 1)
        # Completion rate = (2 / 4) * 100 = 50.00%
        self.assertEqual(stats['completionRate'], 50.0)
        # Revenue = 2 completed * 400.00 = 800.00
        self.assertEqual(stats['totalRevenue'], 800.00)
        # Active patients = 2 (Alice & Bob)
        self.assertEqual(stats['activePatients'], 2)

        # Upcoming appointments
        upcoming = res.data['upcomingAppointments']
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0]['patientName'], "Bob Walker")
        self.assertEqual(upcoming[0]['timeSlot'], "14:00 - 14:30")
        self.assertEqual(upcoming[0]['status'], "confirmed")
        self.assertEqual(upcoming[0]['notes'], "Follow up review")

    def test_13_dashboard_auth_permissions(self):
        """13. Dashboard endpoint blocks unauthenticated users and non-doctors."""
        url = reverse('doctors:doctor_dashboard')
        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.patient_1_user)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.hospital_admin_user)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # C. Doctor Patient Directory Tests
    # =========================================================================

    def test_14_patient_directory_lists_unique_patients_and_dependents(self):
        """14. Directory lists unique patients and treats dependents as distinct entities."""
        today = date.today()
        # Alice visit 1
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_1_user,
            patient_profile=self.patient_1_profile,
            hospital=self.hospital,
            date=today - timedelta(days=10),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED,
            notes="Initial consult"
        )
        # Alice visit 2 (latest notes)
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_1_user,
            patient_profile=self.patient_1_profile,
            hospital=self.hospital,
            date=today - timedelta(days=2),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.COMPLETED,
            notes="Blood pressure normal. Refill prescription."
        )
        # Dependent Tommy (child) visit
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_1_user,
            dependent=self.dependent_child,
            hospital=self.hospital,
            date=today - timedelta(days=5),
            time_slot="11:00 - 11:30",
            status=AppointmentStatus.COMPLETED,
            notes="Pediatric checkup"
        )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_patients')
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 2)  # Alice and Tommy distinct
        results = res.data['results']

        alice_entry = next((p for p in results if p['patientName'] == "Alice Patient"), None)
        self.assertIsNotNone(alice_entry)
        self.assertEqual(alice_entry['patientId'], str(self.patient_1_profile.id))
        self.assertEqual(alice_entry['totalVisits'], 2)
        self.assertEqual(alice_entry['firstVisitDate'], str(today - timedelta(days=10)))
        self.assertEqual(alice_entry['lastVisitDate'], str(today - timedelta(days=2)))
        self.assertEqual(alice_entry['latestNotes'], "Blood pressure normal. Refill prescription.")
        self.assertEqual(alice_entry['gender'], "Female")
        self.assertEqual(alice_entry['bloodGroup'], "O+")

        tommy_entry = next((p for p in results if p['patientName'] == "Tommy Patient"), None)
        self.assertIsNotNone(tommy_entry)
        self.assertEqual(tommy_entry['patientId'], str(self.dependent_child.id))
        self.assertEqual(tommy_entry['totalVisits'], 1)
        self.assertEqual(tommy_entry['latestNotes'], "Pediatric checkup")
        self.assertEqual(tommy_entry['gender'], "Male")

    def test_15_patient_directory_search_filter(self):
        """15. Search filters patient roster by name and phone."""
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_1_user,
            patient_profile=self.patient_1_profile,
            hospital=self.hospital,
            date=date.today(),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED
        )
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_2_user,
            patient_profile=self.patient_2_profile,
            hospital=self.hospital,
            date=date.today(),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.COMPLETED
        )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_patients')

        # Search for "Alice"
        res_alice = self.client.get(f"{url}?search=Alice")
        self.assertEqual(res_alice.data['count'], 1)
        self.assertEqual(res_alice.data['results'][0]['patientName'], "Alice Patient")

        # Search for Bob by phone digits
        res_bob = self.client.get(f"{url}?search=2220002")
        self.assertEqual(res_bob.data['count'], 1)
        self.assertEqual(res_bob.data['results'][0]['patientName'], "Bob Walker")

        # Search non-matching
        res_none = self.client.get(f"{url}?search=NonExistent")
        self.assertEqual(res_none.data['count'], 0)

    def test_16_patient_directory_doctor_isolation(self):
        """16. Doctor A CANNOT see Doctor B's patients or Doctor B's clinical notes."""
        # Patient 2 visits Doctor B ONLY
        Appointment.objects.create(
            doctor=self.doctor_b,
            booked_by=self.patient_2_user,
            patient_profile=self.patient_2_profile,
            hospital=self.hospital,
            date=date.today(),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED,
            notes="Confidential neurological notes for Doctor B only"
        )
        # Patient 1 visits Doctor A
        Appointment.objects.create(
            doctor=self.doctor_a,
            booked_by=self.patient_1_user,
            patient_profile=self.patient_1_profile,
            hospital=self.hospital,
            date=date.today(),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.COMPLETED,
            notes="Doctor A notes"
        )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_patients')
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['patientName'], "Alice Patient")
        # Ensure Bob Walker is NOT exposed
        names = [p['patientName'] for p in res.data['results']]
        self.assertNotIn("Bob Walker", names)
        # Ensure Doctor B notes are NOT exposed
        raw_content = str(res.data)
        self.assertNotIn("Confidential neurological notes", raw_content)

    def test_17_patient_directory_pagination(self):
        """17. Patient directory respects page and page_size parameters."""
        for i in range(15):
            u = User.objects.create_user(
                email=f"listpat{i}@example.com",
                role=UserRole.PATIENT,
                phone=f"+97150000{i:04d}",
                name=f"Patient {i:02d}"
            )
            prof = PatientProfile.objects.create(user=u)
            Appointment.objects.create(
                doctor=self.doctor_a,
                booked_by=u,
                patient_profile=prof,
                hospital=self.hospital,
                date=date.today() - timedelta(days=i),
                time_slot="09:00 - 09:30",
                status=AppointmentStatus.COMPLETED
            )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_patients')

        # Default page_size is 10
        res_default = self.client.get(url)
        self.assertEqual(res_default.data['count'], 15)
        self.assertEqual(len(res_default.data['results']), 10)

        # Page 2
        res_page2 = self.client.get(f"{url}?page=2&page_size=10")
        self.assertEqual(len(res_page2.data['results']), 5)

    def test_18_patient_directory_query_efficiency(self):
        """18. Patient directory does not produce N+1 query explosion."""
        for i in range(5):
            u = User.objects.create_user(
                email=f"perfpat{i}@example.com",
                role=UserRole.PATIENT,
                phone=f"+97159999{i:04d}",
                name=f"Perf Patient {i}"
            )
            prof = PatientProfile.objects.create(user=u)
            Appointment.objects.create(
                doctor=self.doctor_a,
                booked_by=u,
                patient_profile=prof,
                hospital=self.hospital,
                date=date.today(),
                time_slot="09:00 - 09:30",
                status=AppointmentStatus.COMPLETED
            )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_patients')

        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Query count bounded: user fetch + single appointments query with select_related
        self.assertLessEqual(len(ctx.captured_queries), 5)

    def test_19_doctor_put_empty_available_days_valid(self):
        """19. Doctor can set available_days to empty list (e.g. on leave)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        res = self.client.put(url, {'available_days': [], 'standard_slots': ['09:00 - 09:30']}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['available_days'], [])
        self.assertEqual(res.data['standard_slots'], ['09:00 - 09:30'])

    def test_20_doctor_patch_only_slots(self):
        """20. Doctor PATCH with only standardSlots preserves existing available_days."""
        DoctorSchedule.objects.create(
            doctor=self.doctor_a,
            available_days=['Monday', 'Wednesday'],
            standard_slots=['09:00 - 09:30'],
            slot_duration_minutes=30
        )
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        res = self.client.patch(url, {'standardSlots': ['14:00 - 14:30', '14:30 - 15:00']}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['available_days'], ['Monday', 'Wednesday'])
        self.assertEqual(res.data['standard_slots'], ['14:00 - 14:30', '14:30 - 15:00'])

    def test_21_client_supplied_doctor_id_ignored(self):
        """21. Client-supplied doctor_id in payload or query is ignored; server enforces request.user."""
        DoctorSchedule.objects.create(
            doctor=self.doctor_b,
            available_days=['Friday'],
            standard_slots=['10:00 - 10:30'],
            slot_duration_minutes=30
        )
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_schedule')
        # Attempt to overwrite Doctor B schedule by passing doctor_id
        res = self.client.put(url, {
            'doctor_id': str(self.doctor_b.id),
            'available_days': ['Sunday'],
            'standard_slots': ['11:00 - 11:30']
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Doctor A's schedule was updated
        sched_a = DoctorSchedule.objects.get(doctor=self.doctor_a)
        self.assertEqual(sched_a.available_days, ['Sunday'])
        # Doctor B's schedule was NOT touched
        sched_b = DoctorSchedule.objects.get(doctor=self.doctor_b)
        self.assertEqual(sched_b.available_days, ['Friday'])

    def test_22_patient_directory_empty_state(self):
        """22. Doctor with no appointments returns empty patient directory cleanly."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_patients')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 0)
        self.assertEqual(res.data['results'], [])

    def test_23_dashboard_query_count_efficiency(self):
        """23. Dashboard KPIs and weekly trend run within a bounded, small query count."""
        today = date.today()
        for i in range(5):
            Appointment.objects.create(
                doctor=self.doctor_a,
                booked_by=self.patient_1_user,
                patient_profile=self.patient_1_profile,
                hospital=self.hospital,
                date=today - timedelta(days=i),
                time_slot="09:00 - 09:30",
                status=AppointmentStatus.COMPLETED
            )

        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('doctors:doctor_dashboard')

        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Under 7 queries total: user auth, doctor check, stats aggregate, primary count, dep count, trend values, upcoming list
        self.assertLessEqual(len(ctx.captured_queries), 7)
