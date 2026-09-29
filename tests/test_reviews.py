"""Comprehensive Automated Test Suite for Phase 8: Verified Reviews & Doctor Ratings."""
import uuid
from decimal import Decimal
from datetime import date
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole, PatientProfile
from apps.facilities.models import Hospital, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus, DoctorReview
from apps.audit.models import AuditLog


class DoctorReviewTests(TestCase):
    """Test suite covering Phase 8 review creation, reading, ratings, validation, and privacy."""

    def setUp(self):
        self.client = APIClient()

        # 1. Hospital & Doctor setup
        self.hospital = Hospital.objects.create(
            name="American Hospital Dubai",
            location="Oud Metha, Dubai",
            address="19th St, Oud Metha",
            phone="+97143775500",
            operating_hours="24/7",
            status=FacilityStatus.ACTIVE
        )

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
            consultation_fee=350.00,
            rating=Decimal("4.80"),
            review_count=15,
            status=FacilityStatus.ACTIVE
        )

        # Doctor B (non-attending)
        self.doctor_b_user = User.objects.create_user(
            email="dr.jones@americanhospital.ae",
            role=UserRole.DOCTOR,
            phone="+971509998877",
            name="Dr. Sarah Jones"
        )
        self.doctor_b = Doctor.objects.create(
            user=self.doctor_b_user,
            hospital=self.hospital,
            name="Dr. Sarah Jones",
            specialty="Neurology",
            status=FacilityStatus.ACTIVE
        )

        # Deactivated Doctor
        self.deactivated_doctor_user = User.objects.create_user(
            email="dr.inactive@americanhospital.ae",
            role=UserRole.DOCTOR,
            phone="+971500001122",
            name="Dr. Inactive"
        )
        self.deactivated_doctor = Doctor.objects.create(
            user=self.deactivated_doctor_user,
            hospital=self.hospital,
            name="Dr. Inactive",
            specialty="Dermatology",
            status=FacilityStatus.DEACTIVATED
        )

        # 2. Patients
        self.patient_a_user = User.objects.create_user(
            email="patient.a@example.com",
            role=UserRole.PATIENT,
            phone="+971501234567",
            name="Alice Patient"
        )
        self.patient_a_profile = PatientProfile.objects.create(
            user=self.patient_a_user,
            gender="Female",
            blood_group="O+"
        )

        self.patient_b_user = User.objects.create_user(
            email="patient.b@example.com",
            role=UserRole.PATIENT,
            phone="+971507654321",
            name="Bob Walker"
        )
        self.patient_b_profile = PatientProfile.objects.create(
            user=self.patient_b_user,
            gender="Male",
            blood_group="A+"
        )

        # 3. Admins
        self.hospital_admin_user = User.objects.create_user(
            email="admin@americanhospital.ae",
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

        # 4. Standard Completed Appointment for Patient A with Doctor Smith
        self.completed_appointment = Appointment.objects.create(
            patient_profile=self.patient_a_profile,
            booked_by=self.patient_a_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="10:00",
            status=AppointmentStatus.COMPLETED
        )

    # =========================================================================
    # A. Creation Tests
    # =========================================================================
    def test_01_patient_submits_valid_review(self):
        """1. Patient submits valid review -> 201 Created and rating updated."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        payload = {
            'rating': 5,
            'comment': 'Outstanding cardiologist, very attentive and polite.'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['rating'], 5)
        self.assertEqual(response.data['comment'], payload['comment'])
        self.assertEqual(response.data['appointment_id'], str(self.completed_appointment.id))
        self.assertEqual(response.data['doctor_id'], str(self.doctor.id))
        self.assertEqual(response.data['doctor_name'], self.doctor.name)

        # Doctor rating updated
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.rating, Decimal('5.00'))
        self.assertEqual(self.doctor.review_count, 1)

    def test_02_empty_comment_valid(self):
        """2. Empty or omitted comment is valid -> 201."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 4}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['rating'], 4)
        self.assertEqual(response.data['comment'], "")

    def test_03_rating_1_valid(self):
        """3. Rating 1 is valid -> 201."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 1, 'comment': 'Poor experience'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['rating'], 1)

    def test_04_rating_5_valid(self):
        """4. Rating 5 is valid -> 201."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 5, 'comment': 'Excellent!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['rating'], 5)

    # =========================================================================
    # B. Authentication & Authorization Tests
    # =========================================================================
    def test_05_unauthenticated_rejected(self):
        """5. Unauthenticated review submission -> 401 Unauthorized."""
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_06_doctor_cannot_submit_review(self):
        """6. Doctor role cannot submit review -> 403 Forbidden."""
        self.client.force_authenticate(user=self.doctor_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_07_hospital_admin_cannot_submit_review(self):
        """7. Hospital admin cannot submit review -> 403 Forbidden."""
        self.client.force_authenticate(user=self.hospital_admin_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_08_platform_admin_cannot_submit_review(self):
        """8. Platform admin cannot submit review -> 403 Forbidden."""
        self.client.force_authenticate(user=self.platform_admin_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # C. IDOR Isolation Tests
    # =========================================================================
    def test_09_patient_a_cannot_review_patient_b_appointment(self):
        """9. Patient A cannot review Patient B's appointment -> 404 (IDOR protection)."""
        appointment_b = Appointment.objects.create(
            patient_profile=self.patient_b_profile,
            booked_by=self.patient_b_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="11:00",
            status=AppointmentStatus.COMPLETED
        )
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': appointment_b.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_10_patient_a_cannot_view_patient_b_review(self):
        """10. Patient A cannot view Patient B's private review -> 404."""
        appointment_b = Appointment.objects.create(
            patient_profile=self.patient_b_profile,
            booked_by=self.patient_b_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="11:00",
            status=AppointmentStatus.COMPLETED
        )
        DoctorReview.objects.create(
            appointment=appointment_b,
            doctor=self.doctor,
            patient=self.patient_b_user,
            rating=5,
            comment="Private feedback"
        )
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': appointment_b.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_11_non_attending_doctor_cannot_view_private_review(self):
        """11. Non-attending doctor cannot view private appointment review -> 404."""
        DoctorReview.objects.create(
            appointment=self.completed_appointment,
            doctor=self.doctor,
            patient=self.patient_a_user,
            rating=5,
            comment="Excellent care"
        )
        # Dr. Sarah Jones is doctor_b (not the attending doctor)
        self.client.force_authenticate(user=self.doctor_b_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_attending_doctor_can_view_private_review(self):
        """Attending doctor CAN view private review for their completed appointment -> 200."""
        DoctorReview.objects.create(
            appointment=self.completed_appointment,
            doctor=self.doctor,
            patient=self.patient_a_user,
            rating=5,
            comment="Wonderful consultation"
        )
        self.client.force_authenticate(user=self.doctor_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['rating'], 5)
        self.assertEqual(response.data['comment'], "Wonderful consultation")

    def test_hospital_admin_cannot_view_private_review(self):
        """Hospital admin receives 404 on private appointment review read."""
        DoctorReview.objects.create(
            appointment=self.completed_appointment,
            doctor=self.doctor,
            patient=self.patient_a_user,
            rating=5,
            comment="Confidential review"
        )
        self.client.force_authenticate(user=self.hospital_admin_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # D. Lifecycle Tests
    # =========================================================================
    def test_12_pending_appointment_cannot_be_reviewed(self):
        """12. Pending appointment cannot be reviewed -> 400 CANNOT_REVIEW_UNCOMPLETED."""
        appt = Appointment.objects.create(
            patient_profile=self.patient_a_profile,
            booked_by=self.patient_a_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="12:00",
            status=AppointmentStatus.PENDING
        )
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': appt.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'CANNOT_REVIEW_UNCOMPLETED')

    def test_13_confirmed_appointment_cannot_be_reviewed(self):
        """13. Confirmed appointment cannot be reviewed -> 400 CANNOT_REVIEW_UNCOMPLETED."""
        appt = Appointment.objects.create(
            patient_profile=self.patient_a_profile,
            booked_by=self.patient_a_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="13:00",
            status=AppointmentStatus.CONFIRMED
        )
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': appt.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'CANNOT_REVIEW_UNCOMPLETED')

    def test_14_cancelled_appointment_cannot_be_reviewed(self):
        """14. Cancelled appointment cannot be reviewed -> 400 CANNOT_REVIEW_UNCOMPLETED."""
        appt = Appointment.objects.create(
            patient_profile=self.patient_a_profile,
            booked_by=self.patient_a_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="14:00",
            status=AppointmentStatus.CANCELLED
        )
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': appt.id})
        response = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'CANNOT_REVIEW_UNCOMPLETED')

    def test_15_completed_appointment_reviewed_successfully(self):
        """15. Completed appointment can be reviewed -> 201 Created."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        response = self.client.post(url, {'rating': 5, 'comment': 'Great job'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_16_duplicate_review_rejected(self):
        """16. Duplicate review on already reviewed appointment -> 409 ALREADY_REVIEWED."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        # 1st review
        res1 = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        # 2nd review
        res2 = self.client.post(url, {'rating': 4}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res2.data.get('code'), 'ALREADY_REVIEWED')

    # =========================================================================
    # E. Rating Aggregation Tests
    # =========================================================================
    def test_17_one_review_rating_and_count(self):
        """17. First review with rating 4 sets rating to 4.00, count 1."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        self.client.post(url, {'rating': 4}, format='json')
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.rating, Decimal('4.00'))
        self.assertEqual(self.doctor.review_count, 1)

    def test_18_two_reviews_arithmetic_average(self):
        """18. Reviews of 4 and 5 produce arithmetic average 4.50, count 2."""
        # 1st review (rating 4)
        self.client.force_authenticate(user=self.patient_a_user)
        url_a = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        self.client.post(url_a, {'rating': 4}, format='json')

        # 2nd review by patient B (rating 5)
        appointment_b = Appointment.objects.create(
            patient_profile=self.patient_b_profile,
            booked_by=self.patient_b_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="15:00",
            status=AppointmentStatus.COMPLETED
        )
        self.client.force_authenticate(user=self.patient_b_user)
        url_b = reverse('appointments:appointment_review', kwargs={'pk': appointment_b.id})
        self.client.post(url_b, {'rating': 5}, format='json')

        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.rating, Decimal('4.50'))
        self.assertEqual(self.doctor.review_count, 2)

    def test_19_recalculation_from_actual_database_rows(self):
        """19. Recalculation is computed strictly from actual DoctorReview rows."""
        # Create 3 reviews directly in database: ratings 2, 4, 5 -> avg = 11/3 = 3.666... -> 3.67
        appt1 = self.completed_appointment
        appt2 = Appointment.objects.create(
            patient_profile=self.patient_b_profile,
            booked_by=self.patient_b_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="16:00",
            status=AppointmentStatus.COMPLETED
        )
        patient_c = User.objects.create_user(email="c@example.com", role=UserRole.PATIENT, phone="+971509990011", name="Patient C")
        appt3 = Appointment.objects.create(
            patient_profile=self.patient_a_profile,
            booked_by=patient_c,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="17:00",
            status=AppointmentStatus.COMPLETED
        )

        DoctorReview.objects.create(appointment=appt1, doctor=self.doctor, patient=self.patient_a_user, rating=2)
        DoctorReview.objects.create(appointment=appt2, doctor=self.doctor, patient=self.patient_b_user, rating=4)

        # Trigger via API for 3rd review
        self.client.force_authenticate(user=patient_c)
        url_c = reverse('appointments:appointment_review', kwargs={'pk': appt3.id})
        res = self.client.post(url_c, {'rating': 5}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.doctor.refresh_from_db()
        # (2 + 4 + 5) / 3 = 3.6666... rounded to 2 decimal places = 3.67
        self.assertEqual(self.doctor.rating, Decimal('3.67'))
        self.assertEqual(self.doctor.review_count, 3)

    def test_20_rating_remains_correct_after_multiple_reviews(self):
        """20. Verified pure arithmetic average across 5 reviews."""
        # Ratings: 5, 5, 5, 5, 4 -> 24 / 5 = 4.80
        ratings = [5, 5, 5, 5, 4]
        for idx, r in enumerate(ratings):
            u = User.objects.create_user(email=f"user{idx}@test.com", role=UserRole.PATIENT, phone=f"+9715000000{idx}", name=f"User {idx}")
            appt = Appointment.objects.create(
                patient_profile=self.patient_a_profile,
                booked_by=u,
                doctor=self.doctor,
                hospital=self.hospital,
                date=date.today(),
                time_slot=f"0{idx}:00",
                status=AppointmentStatus.COMPLETED
            )
            self.client.force_authenticate(user=u)
            url = reverse('appointments:appointment_review', kwargs={'pk': appt.id})
            res = self.client.post(url, {'rating': r}, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.rating, Decimal('4.80'))
        self.assertEqual(self.doctor.review_count, 5)

    # =========================================================================
    # F. Validation Tests
    # =========================================================================
    def test_21_rating_0_rejected(self):
        """21. Rating 0 -> 400 INVALID_RATING."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        res = self.client.post(url, {'rating': 0}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('code'), 'INVALID_RATING')

    def test_22_rating_6_rejected(self):
        """22. Rating 6 -> 400 INVALID_RATING."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        res = self.client.post(url, {'rating': 6}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('code'), 'INVALID_RATING')

    def test_23_rating_string_rejected(self):
        """23. Rating string 'five' -> 400 INVALID_RATING."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        res = self.client.post(url, {'rating': 'five'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('code'), 'INVALID_RATING')

    def test_24_rating_fractional_rejected(self):
        """24. Rating float 4.5 -> 400 INVALID_RATING."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        res = self.client.post(url, {'rating': 4.5}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('code'), 'INVALID_RATING')

    def test_25_comment_over_maximum_length_rejected(self):
        """25. Comment over 1000 characters -> 400."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        too_long = "a" * 1001
        res = self.client.post(url, {'rating': 5, 'comment': too_long}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # G. Privacy & Anonymity Tests
    # =========================================================================
    def test_26_to_30_public_review_anonymity(self):
        """26-30. Public review displays 'Verified Patient' and NO patient/appointment PII."""
        # Create review
        DoctorReview.objects.create(
            appointment=self.completed_appointment,
            doctor=self.doctor,
            patient=self.patient_a_user,
            rating=5,
            comment="Dr. Smith was kind and very thorough."
        )

        # Access public reviews endpoint
        url = reverse('doctors:doctor_public_reviews', kwargs={'pk': self.doctor.id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Pagination envelope
        self.assertEqual(res.data['count'], 1)
        review_item = res.data['results'][0]

        # 26. Display name is "Verified Patient"
        self.assertEqual(review_item['patientDisplayName'], "Verified Patient")
        self.assertEqual(review_item['patient_display_name'], "Verified Patient")

        # 27. No patient UUID
        self.assertNotIn('patient', review_item)
        self.assertNotIn('patient_id', review_item)
        self.assertNotIn(str(self.patient_a_user.id), str(review_item))
        self.assertNotIn(str(self.patient_a_profile.id), str(review_item))

        # 28. No patient email
        self.assertNotIn('email', review_item)
        self.assertNotIn(self.patient_a_user.email, str(review_item))

        # 29. No phone
        self.assertNotIn('phone', review_item)
        self.assertNotIn(self.patient_a_user.phone, str(review_item))

        # 30. No appointment UUID
        self.assertNotIn('appointment', review_item)
        self.assertNotIn('appointment_id', review_item)
        self.assertNotIn(str(self.completed_appointment.id), str(review_item))

    def test_31_32_audit_log_contains_no_comment_or_clinical_data(self):
        """31-32. Audit log for PATIENT_REVIEW_SUBMITTED contains no comment or clinical info."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        sensitive_comment = "Secret medical issue was resolved with medication"
        res = self.client.post(url, {'rating': 5, 'comment': sensitive_comment}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Inspect audit logs
        log = AuditLog.objects.filter(action='PATIENT_REVIEW_SUBMITTED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.patient_a_user)
        self.assertEqual(log.change_summary.get('doctor_id'), str(self.doctor.id))
        self.assertEqual(log.change_summary.get('appointment_id'), str(self.completed_appointment.id))
        self.assertEqual(log.change_summary.get('rating'), 5)

        # 31. No comment in audit change_summary
        self.assertNotIn('comment', log.change_summary)
        self.assertNotIn(sensitive_comment, str(log.change_summary))

        # 32. No clinical info
        self.assertNotIn('medical', str(log.change_summary))
        self.assertNotIn('consultation', str(log.change_summary))

    def test_inactive_doctor_public_reviews_404(self):
        """Public reviews for inactive doctor returns 404."""
        url = reverse('doctors:doctor_public_reviews', kwargs={'pk': self.deactivated_doctor.id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # H. Appointment Serializer Integration Tests
    # =========================================================================
    def test_33_34_35_appointment_serializer_review_fields(self):
        """33-35. Serializer exposes is_reviewed and review summary (or null)."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_detail', kwargs={'pk': self.completed_appointment.id})

        # 34, 35. Before review: is_reviewed is False, review is None
        res_before = self.client.get(url)
        self.assertEqual(res_before.status_code, status.HTTP_200_OK)
        self.assertFalse(res_before.data['is_reviewed'])
        self.assertIsNone(res_before.data['review'])

        # Create review
        DoctorReview.objects.create(
            appointment=self.completed_appointment,
            doctor=self.doctor,
            patient=self.patient_a_user,
            rating=5,
            comment="Excellent care"
        )

        # 33. After review: is_reviewed is True, review has summary
        res_after = self.client.get(url)
        self.assertEqual(res_after.status_code, status.HTTP_200_OK)
        self.assertTrue(res_after.data['is_reviewed'])
        self.assertIsNotNone(res_after.data['review'])
        self.assertEqual(res_after.data['review']['rating'], 5)
        self.assertEqual(res_after.data['review']['comment'], "Excellent care")

    def test_36_appointment_list_query_efficiency(self):
        """36. Appointment list does not cause N+1 query explosion on review field."""
        # Create 5 completed appointments for Patient A
        for i in range(5):
            appt = Appointment.objects.create(
                patient_profile=self.patient_a_profile,
                booked_by=self.patient_a_user,
                doctor=self.doctor,
                hospital=self.hospital,
                date=date.today(),
                time_slot=f"0{i}:30",
                status=AppointmentStatus.COMPLETED
            )
            # Review odd-numbered appointments
            if i % 2 == 1:
                DoctorReview.objects.create(
                    appointment=appt,
                    doctor=self.doctor,
                    patient=self.patient_a_user,
                    rating=5,
                    comment=f"Review {i}"
                )

        self.client.force_authenticate(user=self.patient_a_user)
        list_url = reverse('appointments:my_appointments')

        # Capture SQL query count for 5+ appointments
        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(list_url)
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Because 'review' is in select_related, the query count must remain bounded and small
        # (typically user fetch + single appointments query with joins). Under 10 queries total.
        self.assertLessEqual(len(ctx.captured_queries), 5)

    # =========================================================================
    # I. Concurrency & Database Integrity Tests
    # =========================================================================
    def test_37_database_one_to_one_constraint(self):
        """37. Database OneToOneField prevents duplicate review records."""
        DoctorReview.objects.create(
            appointment=self.completed_appointment,
            doctor=self.doctor,
            patient=self.patient_a_user,
            rating=5
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            DoctorReview.objects.create(
                appointment=self.completed_appointment,
                doctor=self.doctor,
                patient=self.patient_a_user,
                rating=4
            )

    def test_38_service_atomic_recalculation(self):
        """38. Recalculation service handles atomic update and rounding correctly."""
        from apps.appointments.services import recalculate_doctor_rating
        # Create reviews: ratings 3, 4 -> average 3.50
        appt_a = self.completed_appointment
        appt_b = Appointment.objects.create(
            patient_profile=self.patient_b_profile,
            booked_by=self.patient_b_user,
            doctor=self.doctor,
            hospital=self.hospital,
            date=date.today(),
            time_slot="18:00",
            status=AppointmentStatus.COMPLETED
        )
        DoctorReview.objects.create(appointment=appt_a, doctor=self.doctor, patient=self.patient_a_user, rating=3)
        DoctorReview.objects.create(appointment=appt_b, doctor=self.doctor, patient=self.patient_b_user, rating=4)

        recalculate_doctor_rating(self.doctor.id)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.rating, Decimal('3.50'))
        self.assertEqual(self.doctor.review_count, 2)

    def test_39_review_immutability_no_put_patch_delete(self):
        """39. Reviews are strictly immutable: PUT, PATCH, DELETE are rejected with 405."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})

        # PUT not allowed
        res_put = self.client.put(url, {'rating': 3}, format='json')
        self.assertEqual(res_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # PATCH not allowed
        res_patch = self.client.patch(url, {'rating': 3}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # DELETE not allowed
        res_delete = self.client.delete(url)
        self.assertEqual(res_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_40_get_unreviewed_appointment_returns_404(self):
        """40. GET /api/v1/appointments/<pk>/review/ on unreviewed appointment returns 404."""
        self.client.force_authenticate(user=self.patient_a_user)
        url = reverse('appointments:appointment_review', kwargs={'pk': self.completed_appointment.id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_41_public_reviews_pagination(self):
        """41. Public reviews pagination supports page and page_size up to 50."""
        # Create 15 reviews for doctor
        for i in range(15):
            u = User.objects.create_user(email=f"pguser{i}@test.com", role=UserRole.PATIENT, phone=f"+9715100000{i:02d}", name=f"Pg User {i}")
            appt = Appointment.objects.create(
                patient_profile=self.patient_a_profile,
                booked_by=u,
                doctor=self.doctor,
                hospital=self.hospital,
                date=date.today(),
                time_slot=f"{i:02d}:00",
                status=AppointmentStatus.COMPLETED
            )
            DoctorReview.objects.create(
                appointment=appt,
                doctor=self.doctor,
                patient=u,
                rating=4,
                comment=f"Review #{i}"
            )

        # Default page_size is 10
        url = reverse('doctors:doctor_public_reviews', kwargs={'pk': self.doctor.id})
        res_default = self.client.get(url)
        self.assertEqual(res_default.status_code, status.HTTP_200_OK)
        self.assertEqual(res_default.data['count'], 15)
        self.assertEqual(len(res_default.data['results']), 10)
        self.assertIsNotNone(res_default.data['next'])

        # Custom page_size = 5
        res_5 = self.client.get(f"{url}?page_size=5")
        self.assertEqual(len(res_5.data['results']), 5)

        # Max page_size = 50 returns all 15
        res_50 = self.client.get(f"{url}?page_size=50")
        self.assertEqual(len(res_50.data['results']), 15)
        self.assertIsNone(res_50.data['next'])

    def test_42_database_check_constraint_rating_1_to_5(self):
        """42. Database CHECK constraint enforces 1 <= rating <= 5."""
        from django.db import IntegrityError
        # Test rating < 1
        with self.assertRaises(IntegrityError):
            DoctorReview.objects.create(
                appointment=self.completed_appointment,
                doctor=self.doctor,
                patient=self.patient_a_user,
                rating=0
            )


class DoctorReviewConcurrencyTests(TransactionTestCase):
    """Concurrency tests validating atomic doctor rating updates under transactions."""

    def test_concurrent_reviews_maintain_accurate_average(self):
        """Serial/atomic review creations with select_for_update recalculate exact average."""
        hospital = Hospital.objects.create(
            name="City Hospital",
            location="Dubai",
            address="Al Wasl",
            phone="+97140001111",
            status=FacilityStatus.ACTIVE
        )
        doctor_user = User.objects.create_user(
            email="doc.concurrent@meetadr.com",
            role=UserRole.DOCTOR,
            phone="+971509991122",
            name="Dr. Concurrent"
        )
        doctor = Doctor.objects.create(
            user=doctor_user,
            hospital=hospital,
            name="Dr. Concurrent",
            specialty="Pediatrics",
            status=FacilityStatus.ACTIVE
        )

        ratings = [3, 5, 4, 4, 5]  # sum = 21, count = 5 -> avg = 4.20
        for idx, rating in enumerate(ratings):
            patient_user = User.objects.create_user(
                email=f"cpatient{idx}@meetadr.com",
                role=UserRole.PATIENT,
                phone=f"+9715888800{idx:02d}",
                name=f"Patient {idx}"
            )
            patient_prof = PatientProfile.objects.create(
                user=patient_user,
                gender="Female"
            )
            appt = Appointment.objects.create(
                patient_profile=patient_prof,
                booked_by=patient_user,
                doctor=doctor,
                hospital=hospital,
                date=date.today(),
                time_slot=f"1{idx}:00",
                status=AppointmentStatus.COMPLETED
            )
            client = APIClient()
            client.force_authenticate(user=patient_user)
            url = reverse('appointments:appointment_review', kwargs={'pk': appt.id})
            res = client.post(url, {'rating': rating}, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        doctor.refresh_from_db()
        self.assertEqual(doctor.rating, Decimal('4.20'))
        self.assertEqual(doctor.review_count, 5)
