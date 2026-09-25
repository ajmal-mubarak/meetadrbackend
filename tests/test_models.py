"""MeetAdr Backend Core Model & Constraint Verification Tests."""
import uuid
import datetime
from django.test import TestCase
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from apps.accounts.models import PatientProfile, PatientDependent, UserRole
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus

User = get_user_model()

class CoreModelConstraintTests(TestCase):
    def setUp(self):
        # Create facility
        self.hospital = Hospital.objects.create(
            name="City Care Hospital",
            location="Dubai Healthcare City",
            address="Building 42",
            phone="+97141234567",
            operating_hours="24/7",
            about="Premier healthcare hospital.",
            status=FacilityStatus.ACTIVE
        )
        self.clinic = Clinic.objects.create(
            name="Prime Dental Clinic",
            location="Jumeirah",
            address="Al Wasl Rd",
            primary_specialty="Dentistry",
            phone="+97147654321",
            operating_hours="09:00 - 20:00",
            about="Specialized dental center.",
            status=FacilityStatus.ACTIVE
        )
        # Create users
        self.patient_user = User.objects.create_user(
            email="patient@meetadr.demo",
            name="Sarah Jenkins",
            role=UserRole.PATIENT
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user,
            blood_group="O+",
            emergency_contact="+971501234567"
        )
        self.dependent = PatientDependent.objects.create(
            profile=self.patient_profile,
            name="Leo Jenkins",
            relation="Child",
            dob=datetime.date(2020, 5, 12),
            blood_group="O+"
        )
        # Create doctor
        self.doctor_user = User.objects.create_user(
            email="doctor@meetadr.demo",
            name="Dr. Tariq Al-Mansoor",
            role=UserRole.DOCTOR
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            name="Dr. Tariq Al-Mansoor",
            specialty="Cardiology",
            hospital=self.hospital,
            clinic=None,
            location="Dubai Healthcare City",
            status=FacilityStatus.ACTIVE
        )
        self.schedule = DoctorSchedule.objects.create(
            doctor=self.doctor,
            available_days=["Monday", "Wednesday", "Saturday"],
            standard_slots=["09:00 - 09:30", "10:00 - 10:30"]
        )

    def test_doctor_exclusive_hospital_or_clinic_constraint(self):
        """Doctor cannot belong to BOTH hospital and clinic."""
        with self.assertRaises(IntegrityError):
            Doctor.objects.create(
                name="Dr. Invalid",
                specialty="General",
                hospital=self.hospital,
                clinic=self.clinic,
                location="Dubai"
            )

    def test_doctor_must_belong_to_at_least_one_facility(self):
        """Doctor cannot belong to NEITHER hospital nor clinic."""
        with self.assertRaises(IntegrityError):
            Doctor.objects.create(
                name="Dr. Homeless",
                specialty="General",
                hospital=None,
                clinic=None,
                location="Dubai"
            )

    def test_primary_patient_appointment_creation(self):
        """Primary patient appointment sets booked_by and patient_profile."""
        apt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            dependent=None,
            doctor=self.doctor,
            hospital=self.hospital,
            patient_name_snapshot=self.patient_user.name,
            patient_phone_snapshot="+971501234567",
            patient_email_snapshot=self.patient_user.email,
            specialty_snapshot=self.doctor.specialty,
            date=datetime.date(2026, 10, 5),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.CONFIRMED
        )
        self.assertEqual(apt.booked_by, self.patient_user)
        self.assertEqual(apt.patient_profile, self.patient_profile)
        self.assertIsNone(apt.dependent)

    def test_dependent_appointment_creation(self):
        """Dependent appointment sets booked_by to parent and dependent to child."""
        apt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=None,
            dependent=self.dependent,
            doctor=self.doctor,
            hospital=self.hospital,
            patient_name_snapshot=self.dependent.name,
            patient_phone_snapshot="+971501234567",
            patient_email_snapshot=self.patient_user.email,
            specialty_snapshot=self.doctor.specialty,
            date=datetime.date(2026, 10, 5),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.CONFIRMED
        )
        self.assertEqual(apt.booked_by, self.patient_user)
        self.assertEqual(apt.dependent, self.dependent)
        self.assertIsNone(apt.patient_profile)

    def test_appointment_must_have_either_primary_or_dependent(self):
        """Appointment cannot have both or neither patient identities."""
        # Both primary and dependent
        with self.assertRaises(IntegrityError):
            Appointment.objects.create(
                booked_by=self.patient_user,
                patient_profile=self.patient_profile,
                dependent=self.dependent,
                doctor=self.doctor,
                hospital=self.hospital,
                patient_name_snapshot="Both",
                specialty_snapshot=self.doctor.specialty,
                date=datetime.date(2026, 10, 5),
                time_slot="11:00 - 11:30"
            )

    def test_double_booking_prevention_via_unique_slot_constraint(self):
        """Prevent two active bookings for the same doctor, date, and slot."""
        # First booking succeeds
        Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            patient_name_snapshot="Patient 1",
            specialty_snapshot=self.doctor.specialty,
            date=datetime.date(2026, 10, 12),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.CONFIRMED
        )

        # Second booking for the same slot fails with IntegrityError
        with self.assertRaises(IntegrityError):
            Appointment.objects.create(
                booked_by=self.patient_user,
                patient_profile=self.patient_profile,
                doctor=self.doctor,
                hospital=self.hospital,
                patient_name_snapshot="Patient 2",
                specialty_snapshot=self.doctor.specialty,
                date=datetime.date(2026, 10, 12),
                time_slot="10:00 - 10:30",
                status=AppointmentStatus.CONFIRMED
            )

    def test_cancelled_appointment_frees_slot_for_rebooking(self):
        """A cancelled appointment does not block the slot for re-booking."""
        apt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            patient_name_snapshot="Patient 1",
            specialty_snapshot=self.doctor.specialty,
            date=datetime.date(2026, 10, 19),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.CONFIRMED
        )
        # Cancel the appointment
        apt.status = AppointmentStatus.CANCELLED
        apt.cancel_reason = "Patient reschedule"
        apt.save()

        # Rebooking the same slot should now succeed cleanly
        rebooked = Appointment.objects.create(
            booked_by=self.patient_user,
            dependent=self.dependent,
            doctor=self.doctor,
            hospital=self.hospital,
            patient_name_snapshot="Patient 2",
            specialty_snapshot=self.doctor.specialty,
            date=datetime.date(2026, 10, 19),
            time_slot="10:00 - 10:30",
            status=AppointmentStatus.CONFIRMED
        )
        self.assertIsNotNone(rebooked.id)
        self.assertEqual(rebooked.status, AppointmentStatus.CONFIRMED)
