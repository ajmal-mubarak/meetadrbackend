"""Test Suite for Platform Administrator Reports & Analytics (Phase 11 - Scope C)."""
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole, PatientProfile
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor
from apps.appointments.models import Appointment, AppointmentStatus
from apps.onboarding.models import ProviderRequest, ProviderType, RequestStatus


class PlatformAdminReportsAPITests(TestCase):
    """Integration test suite for /api/v1/admin/reports/."""

    def setUp(self):
        self.client = APIClient()

        # 1. Platform Superadmin & Staff
        self.admin_user = User.objects.create_user(
            email="platform.admin@meetadr.com",
            name="Super Admin",
            password="AdminPassword2026!",
            role=UserRole.ADMIN,
            is_staff=True
        )
        self.staff_user = User.objects.create_user(
            email="staff.user@meetadr.com",
            name="Staff User",
            password="StaffPassword2026!",
            role=UserRole.PATIENT,
            is_staff=True
        )

        # 2. Non-admin roles
        self.patient_user = User.objects.create_user(
            email="patient.user@meetadr.com",
            name="Patient User",
            password="PatientPassword2026!",
            role=UserRole.PATIENT
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user,
            gender="Female",
            dob=date(1990, 1, 1)
        )

        self.doctor_user = User.objects.create_user(
            email="doctor.user@meetadr.com",
            name="Doctor User",
            password="DoctorPassword2026!",
            role=UserRole.DOCTOR
        )

        self.facility_admin = User.objects.create_user(
            email="admin@hospital-reports.com",
            name="Facility Admin",
            password="FacilityPassword2026!",
            role=UserRole.HOSPITAL
        )

        # 3. Seed Facilities
        self.hospital = Hospital.objects.create(
            name="General Central Hospital",
            location="Dubai Healthcare City",
            address="Street 10",
            phone="+97140003333",
            operating_hours="24/7",
            status=FacilityStatus.ACTIVE,
            admin_user=self.facility_admin
        )
        self.clinic = Clinic.objects.create(
            name="Al Barsha Wellness Clinic",
            location="Al Barsha, Dubai",
            address="Al Barsha 1",
            primary_specialty="Dermatology",
            phone="+97140004444",
            operating_hours="08:00 - 20:00",
            status=FacilityStatus.ACTIVE
        )

        # 4. Seed Doctors
        self.doctor_a = Doctor.objects.create(
            user=self.doctor_user,
            name="Dr. Omar Khaled",
            specialty="Cardiology",
            hospital=self.hospital,
            location="Dubai Healthcare City",
            consultation_fee=Decimal("500.00"),
            status=FacilityStatus.ACTIVE
        )
        self.doctor_b = Doctor.objects.create(
            name="Dr. Mona Salem",
            specialty="Dermatology",
            clinic=self.clinic,
            location="Al Barsha, Dubai",
            consultation_fee=Decimal("350.00"),
            status=FacilityStatus.ACTIVE
        )

        # 5. Seed Appointments across time periods
        today = date.today()
        # Today appointment
        Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor_a,
            hospital=self.hospital,
            patient_name_snapshot="Patient User",
            specialty_snapshot="Cardiology",
            date=today,
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.CONFIRMED
        )
        # Completed appointment within 7 days
        Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor_a,
            hospital=self.hospital,
            patient_name_snapshot="Patient User",
            specialty_snapshot="Cardiology",
            date=today - timedelta(days=3),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.COMPLETED
        )
        # Cancelled appointment within 30 days
        Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor_b,
            clinic=self.clinic,
            patient_name_snapshot="Patient User",
            specialty_snapshot="Dermatology",
            date=today - timedelta(days=15),
            time_slot="14:00 - 14:30",
            status=AppointmentStatus.CANCELLED
        )

        # 6. Seed Provider Request
        ProviderRequest.objects.create(
            name="New Hope Clinic",
            provider_type=ProviderType.CLINIC,
            contact_person="Director",
            email="contact@newhope.ae",
            contact_number="+971509998888",
            location="Dubai",
            status=RequestStatus.PENDING
        )

        self.reports_url = reverse('admin_onboarding:admin_reports')

    # =========================================================================
    # AUTHORIZATION TESTS
    # =========================================================================

    def test_01_anonymous_denied(self):
        """1. Anonymous requests to reports are rejected with 401."""
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_02_non_admin_roles_denied(self):
        """2. Patient, doctor, and facility admin roles are rejected with 403."""
        for user in [self.patient_user, self.doctor_user, self.facility_admin]:
            self.client.force_authenticate(user=user)
            response = self.client.get(self.reports_url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_03_platform_admin_and_staff_allowed(self):
        """3. Platform admin and is_staff users receive 200 OK."""
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get(self.reports_url)
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.staff_user)
        res_staff = self.client.get(self.reports_url)
        self.assertEqual(res_staff.status_code, status.HTTP_200_OK)

    # =========================================================================
    # METRICS CONTENT TESTS
    # =========================================================================

    def test_04_reports_response_contains_expected_frontend_structure(self):
        """4. Reports response contains exact metrics expected by AdminDashboard & AdminReports."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Overview counts
        self.assertEqual(data['totalDoctors'], 2)
        self.assertEqual(data['totalHospitals'], 1)
        self.assertEqual(data['totalClinics'], 1)
        self.assertEqual(data['totalAppointments'], 3)
        self.assertEqual(data['providerRequestsCount'], 1)

        # Summary rolling counts
        self.assertIn('summary', data)
        summary = data['summary']
        self.assertEqual(summary['daily'], 1)
        self.assertEqual(summary['weekly'], 2)
        self.assertEqual(summary['monthly'], 3)
        self.assertEqual(summary['total'], 3)

        # Specialty breakdown
        self.assertIn('bySpecialty', data)
        specialties = {s['specialty']: s['count'] for s in data['bySpecialty']}
        self.assertEqual(specialties.get('Cardiology'), 2)
        self.assertEqual(specialties.get('Dermatology'), 1)

        # Doctor breakdown
        self.assertIn('byDoctor', data)
        doctors = {d['name']: d['count'] for d in data['byDoctor']}
        self.assertEqual(doctors.get('Dr. Omar Khaled'), 2)
        self.assertEqual(doctors.get('Dr. Mona Salem'), 1)

        # Hospital breakdown
        self.assertIn('byHospital', data)
        facilities = {f['facility']: f['count'] for f in data['byHospital']}
        self.assertEqual(facilities.get('General Central Hospital'), 2)
        self.assertEqual(facilities.get('Al Barsha Wellness Clinic'), 1)

        # Status breakdown
        self.assertIn('appointmentsByStatus', data)
        status_map = {item['status']: item['count'] for item in data['appointmentsByStatus']}
        self.assertEqual(status_map.get('Confirmed'), 1)
        self.assertEqual(status_map.get('Completed'), 1)
        self.assertEqual(status_map.get('Cancelled'), 1)

        # Gross revenue reporting
        self.assertEqual(Decimal(data['grossConsultationRevenue']), Decimal("500.00"))

    def test_05_no_patient_phi_or_clinical_notes_leaked_in_reports(self):
        """5. Reports endpoint does not leak patient medical notes, diagnoses, or prescriptions."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        resp_str = str(response.data).lower()
        for forbidden in ['diagnosis', 'prescription', 'blood_group', 'allergies', 'password', 'token', 'ssn']:
            self.assertNotIn(forbidden, resp_str)
