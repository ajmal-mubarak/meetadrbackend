"""PostgreSQL Concurrency Test Suite for Appointments and Prescriptions."""
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from django.db import connection
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole, PatientProfile
from apps.facilities.models import Hospital, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus
from apps.prescriptions.models import Prescription, PrescriptionStatus

class PostgreSQLConcurrencyValidationTests(TransactionTestCase):
    """
    Validates PostgreSQL database-level partial unique constraints and concurrency
    safety under true concurrent thread execution.
    """

    def setUp(self):
        # 1. Facility
        self.hospital = Hospital.objects.create(
            name="Concurrency Testing Hospital",
            location="Dubai Healthcare City",
            address="Building 10",
            phone="+97140001111",
            status=FacilityStatus.ACTIVE
        )

        # 2. Doctor User & Profile
        self.doc_user = User.objects.create_user(
            email="dr.concurrent.pg@meetadr.com",
            name="Dr. PG Concurrency",
            role=UserRole.DOCTOR,
            password="StrongPassword123!"
        )
        self.doctor = Doctor.objects.create(
            user=self.doc_user,
            hospital=self.hospital,
            name="Dr. PG Concurrency",
            specialty="Cardiology",
            status=FacilityStatus.ACTIVE
        )
        # Doctor Schedule (Mondays available, slots 09:00 AM, 10:00 AM)
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            available_days=["Monday"],
            standard_slots=["09:00 AM", "10:00 AM"],
            slot_duration_minutes=30
        )

        # 3. Two distinct patients
        self.patient_1 = User.objects.create_user(
            email="patient.pg1@meetadr.com",
            name="Patient PG One",
            role=UserRole.PATIENT,
            password="StrongPassword123!"
        )
        self.patient_1_profile = PatientProfile.objects.create(user=self.patient_1)

        self.patient_2 = User.objects.create_user(
            email="patient.pg2@meetadr.com",
            name="Patient PG Two",
            role=UserRole.PATIENT,
            password="StrongPassword123!"
        )
        self.patient_2_profile = PatientProfile.objects.create(user=self.patient_2)

        # Target future Monday
        today = date.today()
        days_ahead = (0 - today.weekday()) % 7
        if days_ahead <= 0:
            days_ahead += 7
        self.target_date = today + timedelta(days=days_ahead)

    def test_01_concurrent_appointment_booking_same_slot(self):
        """
        Step 5 Validation:
        Two concurrent booking requests attempting to book the SAME DOCTOR,
        SAME DATE, and SAME TIME SLOT against PostgreSQL.
        - Database-level unique constraint prevents duplicates.
        - Exactly ONE active appointment exists afterward.
        - The losing request receives HTTP 409 Conflict.
        - No unhandled IntegrityError escapes.
        """
        url = reverse('appointments:appointment_booking')
        payload = {
            "doctor_id": str(self.doctor.id),
            "date": str(self.target_date),
            "time_slot": "09:00 AM",
            "notes": "Concurrent slot booking test"
        }

        results = []

        def book_slot(user):
            # Close existing connection to ensure thread gets its own db connection
            connection.close()
            client = APIClient()
            client.force_authenticate(user=user)
            response = client.post(url, payload, format='json')
            return response.status_code, response.data

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(book_slot, self.patient_1)
            f2 = executor.submit(book_slot, self.patient_2)
            results.append(f1.result())
            results.append(f2.result())

        status_codes = [r[0] for r in results]
        
        # Verify exactly one 201 Created and one 409 Conflict
        self.assertIn(status.HTTP_201_CREATED, status_codes)
        self.assertIn(status.HTTP_409_CONFLICT, status_codes)

        # Verify losing request payload details
        losing_res = next(r[1] for r in results if r[0] == status.HTTP_409_CONFLICT)
        self.assertEqual(losing_res.get('code'), "SLOT_ALREADY_BOOKED")

        # Verify database state in PostgreSQL: exactly 1 active appointment exists
        active_count = Appointment.objects.filter(
            doctor=self.doctor,
            date=self.target_date,
            time_slot="09:00 AM",
            status__in=[AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING]
        ).count()
        self.assertEqual(active_count, 1)

    def test_02_concurrent_prescription_creation_same_appointment(self):
        """
        Step 6 Validation:
        Two concurrent prescription creation requests for the SAME COMPLETED appointment.
        - PostgreSQL unique constraint unique_active_prescription_per_appointment prevents duplicates.
        - Exactly ONE active prescription exists afterward.
        - The losing request receives HTTP 409 Conflict.
        """
        # Create a completed appointment
        appointment = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.patient_1_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            patient_name_snapshot="Patient PG One",
            specialty_snapshot="Cardiology",
            date=self.target_date,
            time_slot="10:00 AM",
            status=AppointmentStatus.COMPLETED
        )

        url = reverse('prescriptions:prescription-create')
        payload = {
            "appointment_id": str(appointment.id),
            "diagnosis": "Hypertension Stage 1",
            "instructions": "Take medication with water",
            "medications": [
                {
                    "medication_name": "Amlodipine",
                    "dosage": "5 mg",
                    "frequency": "Once daily",
                    "duration": "30 days"
                }
            ]
        }

        results = []

        def create_prescription():
            connection.close()
            client = APIClient()
            client.force_authenticate(user=self.doc_user)
            response = client.post(url, payload, format='json')
            return response.status_code, response.data

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(create_prescription)
            f2 = executor.submit(create_prescription)
            results.append(f1.result())
            results.append(f2.result())

        status_codes = [r[0] for r in results]

        # Verify exactly one 201 Created and one 409 Conflict
        self.assertIn(status.HTTP_201_CREATED, status_codes)
        self.assertIn(status.HTTP_409_CONFLICT, status_codes)

        # Verify database state in PostgreSQL: exactly 1 active prescription exists
        active_rx_count = Prescription.objects.filter(
            appointment=appointment,
            status=PrescriptionStatus.ACTIVE
        ).count()
        self.assertEqual(active_rx_count, 1)
