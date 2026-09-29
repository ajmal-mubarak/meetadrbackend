"""Comprehensive Automated Test Suite for Phase 10: User Notifications & Event Engine."""
import uuid
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.test import TestCase
from django.urls import reverse
from django.db import transaction, IntegrityError
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole, PatientProfile, PatientDependent, RelationType
from apps.facilities.models import Hospital, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus, DoctorReview
from apps.prescriptions.models import Prescription, PrescriptionStatus
from apps.onboarding.models import ProviderRequest, ProviderType, RequestStatus, ProviderInvitationToken
from apps.notifications.models import Notification, NotificationType
from apps.notifications.services import (
    create_notification,
    notify_appointment_booked,
    notify_appointment_cancelled,
    notify_appointment_completed,
    notify_prescription_ready,
    notify_prescription_cancelled,
    notify_review_submitted,
    notify_provider_request_submitted,
    notify_facility_setup_completed,
)


class NotificationTests(TestCase):
    """Test suite covering Phase 10 notification endpoints, security, and event engine."""

    def setUp(self):
        self.client = APIClient()

        # 1. Hospital & Facility Admin
        self.facility_admin_user = User.objects.create_user(
            email="admin@americanhospital.ae",
            role=UserRole.HOSPITAL,
            phone="+971501110000",
            name="Hospital Admin"
        )
        self.hospital = Hospital.objects.create(
            admin_user=self.facility_admin_user,
            name="American Hospital Dubai",
            location="Oud Metha, Dubai",
            address="19th St, Oud Metha",
            phone="+97143775500",
            operating_hours="24/7",
            status=FacilityStatus.ACTIVE
        )

        # 2. Attending Doctor with User Account
        self.doctor_user = User.objects.create_user(
            email="dr.smith@americanhospital.ae",
            role=UserRole.DOCTOR,
            phone="+971501112233",
            name="Dr. John Smith"
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            hospital=self.hospital,
            name="Dr. John Smith",
            specialty="Cardiology",
            experience_years=12,
            consultation_fee=Decimal("350.00"),
            rating=Decimal("4.80"),
            review_count=15,
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            available_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            standard_slots=["09:00 - 09:30", "10:00 - 10:30"],
            slot_duration_minutes=30
        )

        # 3. Patient Account & Dependent
        self.patient_user = User.objects.create_user(
            email="patient.alice@example.com",
            role=UserRole.PATIENT,
            phone="+971502223344",
            name="Alice Smith"
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user,
            dob="1992-05-10",
            gender="Female"
        )
        self.dependent = PatientDependent.objects.create(
            profile=self.patient_profile,
            name="Tommy Smith",
            relation=RelationType.CHILD,
            dob="2018-08-15",
            gender="Male"
        )

        # 4. Second Patient (For IDOR / Isolation tests)
        self.patient_b_user = User.objects.create_user(
            email="patient.bob@example.com",
            role=UserRole.PATIENT,
            phone="+971503334455",
            name="Bob Brown"
        )
        self.patient_b_profile = PatientProfile.objects.create(
            user=self.patient_b_user,
            dob="1988-11-20",
            gender="Male"
        )

        # 5. Platform Admin
        self.platform_admin_user = User.objects.create_user(
            email="superadmin@meetadr.ae",
            role=UserRole.ADMIN,
            phone="+971500001122",
            name="Platform Superadmin",
            is_staff=True
        )

    # =========================================================================
    # A. AUTHENTICATION & REST ENDPOINTS
    # =========================================================================

    def test_anonymous_access_denied(self):
        """Anonymous access to all notification endpoints must yield 401 Unauthorized."""
        list_url = reverse('notifications:notification-list')
        count_url = reverse('notifications:notification-unread-count')
        read_all_url = reverse('notifications:notification-read-all')
        single_read_url = reverse('notifications:notification-mark-read', kwargs={'pk': uuid.uuid4()})

        self.assertEqual(self.client.get(list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(count_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(read_all_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.patch(single_read_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_list_and_ownership_isolation(self):
        """Authenticated user only sees their own notifications, never another user's."""
        notif_a = Notification.objects.create(
            user=self.patient_user,
            title="Notification A",
            description="Details for A",
            notification_type=NotificationType.APPOINTMENT,
            link="/patient/bookings"
        )
        notif_b = Notification.objects.create(
            user=self.patient_b_user,
            title="Notification B",
            description="Details for B",
            notification_type=NotificationType.PRESCRIPTION,
            link="/patient/bookings"
        )

        self.client.force_authenticate(user=self.patient_user)
        res = self.client.get(reverse('notifications:notification-list'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], str(notif_a.id))
        self.assertEqual(results[0]['title'], "Notification A")

        # Patient B listing
        self.client.force_authenticate(user=self.patient_b_user)
        res_b = self.client.get(reverse('notifications:notification-list'))
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_b.data['results']), 1)
        self.assertEqual(res_b.data['results'][0]['id'], str(notif_b.id))

    def test_notification_serializer_camelcase_contract(self):
        """Serializer output maps model fields to frontend-expected camelCase and aliases."""
        notif = Notification.objects.create(
            user=self.patient_user,
            title="Appointment Confirmed",
            description="Dr. John Smith at American Hospital Dubai • 2026-10-15 at 09:00 - 09:30",
            notification_type=NotificationType.APPOINTMENT,
            link="/patient/bookings",
            is_read=False
        )

        self.client.force_authenticate(user=self.patient_user)
        res = self.client.get(reverse('notifications:notification-list'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        item = res.data['results'][0]

        # Field verifications
        self.assertEqual(item['id'], str(notif.id))
        self.assertEqual(item['title'], "Appointment Confirmed")
        self.assertEqual(item['notificationType'], "appointment")
        self.assertEqual(item['type'], "appointment")
        self.assertEqual(item['link'], "/patient/bookings")
        self.assertFalse(item['isRead'])
        self.assertTrue(item['unread'])
        self.assertIn('createdAt', item)
        self.assertIn('time', item)

    def test_unread_count_endpoint(self):
        """GET /api/v1/notifications/unread-count/ returns the exact number of unread notifications."""
        Notification.objects.create(
            user=self.patient_user,
            title="N1",
            description="D1",
            is_read=False
        )
        Notification.objects.create(
            user=self.patient_user,
            title="N2",
            description="D2",
            is_read=False
        )
        Notification.objects.create(
            user=self.patient_user,
            title="N3",
            description="D3",
            is_read=True
        )

        self.client.force_authenticate(user=self.patient_user)
        res = self.client.get(reverse('notifications:notification-unread-count'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['unreadCount'], 2)

    def test_mark_single_read_and_idempotency(self):
        """PATCH /api/v1/notifications/<id>/read/ marks is_read=True and is idempotent."""
        notif = Notification.objects.create(
            user=self.patient_user,
            title="N1",
            description="D1",
            is_read=False
        )

        self.client.force_authenticate(user=self.patient_user)
        url = reverse('notifications:notification-mark-read', kwargs={'pk': notif.id})

        # First call -> marks read
        res = self.client.patch(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['isRead'])
        self.assertFalse(res.data['unread'])

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

        # Second call -> idempotent 200
        res2 = self.client.patch(url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data['isRead'])

    def test_cross_user_mark_read_returns_404(self):
        """Attempting to mark another user's notification as read returns 404 (IDOR prevention)."""
        notif_a = Notification.objects.create(
            user=self.patient_user,
            title="Patient A Notice",
            description="D1",
            is_read=False
        )

        # Authenticate as Patient B
        self.client.force_authenticate(user=self.patient_b_user)
        url = reverse('notifications:notification-mark-read', kwargs={'pk': notif_a.id})
        res = self.client.patch(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Verify not modified
        notif_a.refresh_from_db()
        self.assertFalse(notif_a.is_read)

    def test_mark_all_read_affects_only_current_user(self):
        """POST /api/v1/notifications/read-all/ updates only the current user's notifications."""
        # Patient A: 3 unread
        for i in range(3):
            Notification.objects.create(user=self.patient_user, title=f"A{i}", description="D", is_read=False)

        # Patient B: 2 unread
        for i in range(2):
            Notification.objects.create(user=self.patient_b_user, title=f"B{i}", description="D", is_read=False)

        self.client.force_authenticate(user=self.patient_user)
        res = self.client.post(reverse('notifications:notification-read-all'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['markedReadCount'], 3)
        self.assertEqual(res.data['unreadCount'], 0)

        # Verify Patient A notifications are all read
        self.assertEqual(Notification.objects.filter(user=self.patient_user, is_read=False).count(), 0)

        # Verify Patient B notifications remain unread
        self.assertEqual(Notification.objects.filter(user=self.patient_b_user, is_read=False).count(), 2)

    def test_filter_by_unread_query_param(self):
        """GET /api/v1/notifications/?unread=true returns only unread notifications."""
        Notification.objects.create(user=self.patient_user, title="Unread", description="D", is_read=False)
        Notification.objects.create(user=self.patient_user, title="Read", description="D", is_read=True)

        self.client.force_authenticate(user=self.patient_user)
        res = self.client.get(reverse('notifications:notification-list') + '?unread=true')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)
        self.assertEqual(res.data['results'][0]['title'], "Unread")

    # =========================================================================
    # B. APPOINTMENT EVENT NOTIFICATIONS
    # =========================================================================

    def test_appointment_booking_notifies_patient_and_doctor(self):
        """Booking an appointment creates safe in-app notifications for patient and doctor."""
        self.client.force_authenticate(user=self.patient_user)
        booking_url = reverse('appointments:appointment_booking')
        payload = {
            "doctor_id": str(self.doctor.id),
            "date": "2026-10-15",
            "time_slot": "09:00 - 09:30",
            "notes": "Regular heart checkup."
        }
        res = self.client.post(booking_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 1. Patient notification
        patient_notif = Notification.objects.filter(user=self.patient_user).first()
        self.assertIsNotNone(patient_notif)
        self.assertEqual(patient_notif.title, "Appointment Confirmed")
        self.assertIn("Dr. John Smith", patient_notif.description)
        self.assertEqual(patient_notif.notification_type, NotificationType.APPOINTMENT)
        self.assertNotIn("Regular heart checkup.", patient_notif.description)  # Zero clinical notes leakage

        # 2. Doctor notification
        doctor_notif = Notification.objects.filter(user=self.doctor_user).first()
        self.assertIsNotNone(doctor_notif)
        self.assertEqual(doctor_notif.title, "New Appointment Booked")
        self.assertIn("2026-10-15", doctor_notif.description)

    def test_dependent_appointment_booking_recipient_and_privacy(self):
        """Booking for a dependent dispatches to booked_by with neutral phrasing (zero dependent full name)."""
        self.client.force_authenticate(user=self.patient_user)
        booking_url = reverse('appointments:appointment_booking')
        payload = {
            "doctor_id": str(self.doctor.id),
            "dependent_id": str(self.dependent.id),
            "date": "2026-10-20",
            "time_slot": "10:00 - 10:30",
            "notes": "Child pediatric checkup."
        }
        res = self.client.post(booking_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Notification recipient is the account holder (patient_user)
        patient_notif = Notification.objects.filter(user=self.patient_user).order_by('-created_at').first()
        self.assertIsNotNone(patient_notif)
        self.assertEqual(patient_notif.title, "Appointment Confirmed")
        self.assertEqual(patient_notif.description, "Your appointment for a dependent has been confirmed.")
        self.assertNotIn("Tommy Smith", patient_notif.description)  # Masked per Requirement 14
        self.assertNotIn("Child pediatric checkup", patient_notif.description)

    def test_patient_cancellation_notifies_doctor(self):
        """When a patient cancels an appointment, the attending doctor receives a cancellation notification."""
        appt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date(2026, 10, 22),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.CONFIRMED
        )

        self.client.force_authenticate(user=self.patient_user)
        cancel_url = reverse('appointments:appointment_cancel', kwargs={'pk': appt.id})
        res = self.client.post(cancel_url, {"reason": "Change of travel plans."}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Attending doctor receives cancellation notice
        doctor_notif = Notification.objects.filter(user=self.doctor_user, title="Appointment Cancelled").first()
        self.assertIsNotNone(doctor_notif)
        self.assertIn("cancelled by patient", doctor_notif.description)

    def test_doctor_cancellation_notifies_patient(self):
        """When a doctor cancels an appointment, the patient receives a cancellation notification."""
        appt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date(2026, 10, 23),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.CONFIRMED
        )

        self.client.force_authenticate(user=self.doctor_user)
        cancel_url = reverse('appointments:doctor_appointment_status', kwargs={'pk': appt.id})
        res = self.client.patch(cancel_url, {"status": "cancelled", "reason": "Emergency surgery."}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Patient receives cancellation notice
        patient_notif = Notification.objects.filter(user=self.patient_user, title="Appointment Cancelled").first()
        self.assertIsNotNone(patient_notif)
        self.assertIn("Dr. John Smith", patient_notif.description)

    def test_facility_cancellation_notifies_patient_and_doctor(self):
        """When a facility administrator cancels an appointment, both patient and doctor are notified."""
        appt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date(2026, 10, 24),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.CONFIRMED
        )

        self.client.force_authenticate(user=self.facility_admin_user)
        cancel_url = reverse('appointments:hospital_appointment_cancel', kwargs={'pk': appt.id})
        res = self.client.post(cancel_url, {"reason": "Facility renovation."}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # 1. Patient notification
        patient_notif = Notification.objects.filter(user=self.patient_user, title="Appointment Cancelled").first()
        self.assertIsNotNone(patient_notif)

        # 2. Doctor notification
        doctor_notif = Notification.objects.filter(user=self.doctor_user, title="Appointment Cancelled").first()
        self.assertIsNotNone(doctor_notif)

    def test_appointment_completion_notifies_patient(self):
        """Completing a consultation notifies the patient to leave feedback."""
        appt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date(2026, 10, 25),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.CONFIRMED
        )

        self.client.force_authenticate(user=self.doctor_user)
        complete_url = reverse('appointments:doctor_appointment_status', kwargs={'pk': appt.id})
        res = self.client.patch(complete_url, {"status": "completed"}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        patient_notif = Notification.objects.filter(user=self.patient_user, title="Consultation Completed").first()
        self.assertIsNotNone(patient_notif)
        self.assertIn("completed", patient_notif.description)

    # =========================================================================
    # C. PRESCRIPTION NOTIFICATIONS & PRIVACY
    # =========================================================================

    def test_prescription_issuance_notifies_patient_with_zero_phi(self):
        """Prescription issuance notifies the patient without leaking diagnoses or drug names."""
        appt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date(2026, 10, 26),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED
        )

        self.client.force_authenticate(user=self.doctor_user)
        rx_url = reverse('prescriptions:prescription-create')
        payload = {
            "appointment_id": str(appt.id),
            "diagnosis": "Hypertension Stage 2",
            "instructions": "Take daily in the morning with food.",
            "medications": [
                {
                    "medication_name": "Amlodipine Besylate 10mg",
                    "dosage": "10mg",
                    "frequency": "Once daily",
                    "duration": "30 days"
                }
            ]
        }
        res = self.client.post(rx_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        patient_notif = Notification.objects.filter(user=self.patient_user, notification_type=NotificationType.PRESCRIPTION).first()
        self.assertIsNotNone(patient_notif)
        self.assertEqual(patient_notif.title, "Digital Prescription Ready")
        self.assertEqual(
            patient_notif.description,
            "Prescription from Dr. John Smith is ready for pharmacy pickup."
        )
        # Strict Healthcare Privacy Asserts:
        self.assertNotIn("Hypertension", patient_notif.description)
        self.assertNotIn("Amlodipine", patient_notif.description)
        self.assertNotIn("10mg", patient_notif.description)

    def test_prescription_cancellation_notifies_patient(self):
        """Cancelling a prescription notifies the patient."""
        appt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date(2026, 10, 27),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED
        )
        rx = Prescription.objects.create(
            appointment=appt,
            doctor=self.doctor,
            patient=self.patient_user,
            diagnosis="Arrhythmia",
            status=PrescriptionStatus.ACTIVE
        )

        self.client.force_authenticate(user=self.doctor_user)
        cancel_url = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx.id})
        res = self.client.post(cancel_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        patient_notif = Notification.objects.filter(user=self.patient_user, title="Prescription Cancelled").first()
        self.assertIsNotNone(patient_notif)
        self.assertIn("cancelled", patient_notif.description)

    # =========================================================================
    # D. REVIEW NOTIFICATIONS & ANONYMITY
    # =========================================================================

    def test_review_submission_notifies_doctor_anonymously(self):
        """Review submission notifies doctor while strictly preserving patient anonymity."""
        appt = Appointment.objects.create(
            booked_by=self.patient_user,
            patient_profile=self.patient_profile,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date(2026, 10, 28),
            time_slot="09:00 - 09:30",
            status=AppointmentStatus.COMPLETED
        )

        self.client.force_authenticate(user=self.patient_user)
        review_url = reverse('appointments:appointment_review', kwargs={'pk': appt.id})
        payload = {
            "rating": 5,
            "comment": "Doctor Smith was exceptionally thorough and caring."
        }
        res = self.client.post(review_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        doctor_notif = Notification.objects.filter(user=self.doctor_user, title="New Verified Review").first()
        self.assertIsNotNone(doctor_notif)
        self.assertEqual(doctor_notif.description, "A verified patient submitted a 5-star consultation rating.")

        # Strict Reviewer Privacy Asserts:
        self.assertNotIn("Alice", doctor_notif.description)
        self.assertNotIn("Smith", doctor_notif.description)
        self.assertNotIn("exceptionally thorough", doctor_notif.description)  # Review comments omitted
        self.assertNotIn(str(self.patient_user.id), doctor_notif.description)

    # =========================================================================
    # E. PROVIDER ONBOARDING & ADMIN NOTIFICATIONS
    # =========================================================================

    def test_provider_request_notifies_platform_admins_only(self):
        """Submitting a provider request notifies active platform superadministrators/staff."""
        submit_url = reverse('onboarding:provider_request_create')
        payload = {
            "name": "Al Zahra Medical Center",
            "provider_type": "clinic",
            "contact_person": "Dr. Kareem",
            "contact_number": "+971501239876",
            "email": "kareem@alzahra.ae",
            "country": "United Arab Emirates",
            "location": "Al Barsha, Dubai",
            "address": "Sheikh Zayed Road"
        }
        res = self.client.post(submit_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Platform Admin receives notification
        admin_notif = Notification.objects.filter(user=self.platform_admin_user, title="New Provider Application").first()
        self.assertIsNotNone(admin_notif)
        self.assertIn("Al Zahra Medical Center", admin_notif.description)

        # Regular patient or facility admin must NOT receive it
        self.assertFalse(Notification.objects.filter(user=self.patient_user, title="New Provider Application").exists())
        self.assertFalse(Notification.objects.filter(user=self.facility_admin_user, title="New Provider Application").exists())

    def test_facility_setup_completion_welcome_notification(self):
        """Completing account setup creates a welcome notification for the newly activated facility admin."""
        # Setup an invitation token
        new_facility_admin = User.objects.create_user(
            email="manager@newclinic.ae",
            role=UserRole.HOSPITAL,
            phone="+971509871234",
            name="Clinic Manager",
            is_active=False
        )
        invitation = ProviderInvitationToken.objects.create(
            user=new_facility_admin,
            token_hash="sample_hash_token_123",
            expires_at=timezone.now() + timedelta(days=90)
        )

        setup_url = reverse('accounts:provider_setup_complete')
        payload = {
            "token": "valid_token",  # Will be mocked or tested via service directly
            "password": "StrongPassword123!",
            "password_confirm": "StrongPassword123!"
        }

        # Test direct service function call ensuring zero credentials leaked
        notify_facility_setup_completed(new_facility_admin, self.hospital)
        welcome_notif = Notification.objects.filter(user=new_facility_admin, title="Welcome to MeetAdr").first()
        self.assertIsNotNone(welcome_notif)
        self.assertIn("American Hospital Dubai", welcome_notif.description)
        self.assertNotIn("StrongPassword", welcome_notif.description)

    # =========================================================================
    # F. PERFORMANCE & TRANSACTION SAFETY
    # =========================================================================

    def test_unread_count_query_efficiency(self):
        """GET /api/v1/notifications/unread-count/ runs a single SQL count query."""
        for i in range(5):
            Notification.objects.create(user=self.patient_user, title=f"N{i}", description="D", is_read=False)

        self.client.force_authenticate(user=self.patient_user)
        count_url = reverse('notifications:notification-unread-count')

        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(count_url)
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(res.data['unreadCount'], 5)

        # Exactly 1 query (SELECT COUNT(*) FROM meetadr_notifications WHERE ...)
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_transaction_rollback_safety(self):
        """If a parent database transaction rolls back, created notifications do not survive."""
        initial_notif_count = Notification.objects.count()

        try:
            with transaction.atomic():
                create_notification(
                    user=self.patient_user,
                    title="Transaction Rollback Test",
                    description="This should vanish.",
                    notification_type=NotificationType.APPOINTMENT
                )
                # Force an IntegrityError / rollback
                raise IntegrityError("Simulated booking conflict or failure.")
        except IntegrityError:
            pass

        # Verify notification was not saved
        self.assertEqual(Notification.objects.count(), initial_notif_count)
        self.assertFalse(Notification.objects.filter(title="Transaction Rollback Test").exists())
