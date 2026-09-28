"""Automated Test Suite for Phase 7 Clinical / Prescription Workflows."""
from datetime import date
from django.test import TestCase, TransactionTestCase
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole, PatientProfile, PatientDependent
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.doctors.models import Doctor
from apps.appointments.models import Appointment, AppointmentStatus
from apps.prescriptions.models import Prescription, PrescriptionMedication, PrescriptionStatus
from apps.audit.models import AuditLog


class PrescriptionWorkflowTests(TestCase):
    """Test suite covering Phase 7 clinical prescription workflows, authorization, lifecycle, and audit."""

    def setUp(self):
        self.client = APIClient()

        # 1. Facilities
        self.active_hospital = Hospital.objects.create(
            name="American Hospital Dubai",
            location="Oud Metha, Dubai",
            address="19th St, Oud Metha",
            phone="+97143775500",
            operating_hours="24/7",
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
            name="Prime Dental Clinic",
            location="Jumeirah, Dubai",
            address="Jumeirah Beach Road",
            phone="+97143441122",
            status=FacilityStatus.ACTIVE
        )

        # 2. Administrative Users
        self.facility_admin_user = User.objects.create_user(
            email="hospadmin@americanhosp.ae",
            name="Hospital Admin",
            password="StrongPassword2026!",
            role=UserRole.HOSPITAL
        )
        self.active_hospital.admin_user = self.facility_admin_user
        self.active_hospital.save()

        self.platform_admin_user = User.objects.create_user(
            email="platform.admin@meetadr.com",
            name="Platform Superadmin",
            password="StrongPassword2026!",
            role=UserRole.ADMIN,
            is_staff=True
        )

        # 3. Doctors
        # Doctor A @ Active Hospital
        self.doctor_a_user = User.objects.create_user(
            email="doc.jenkins@example.com",
            name="Sarah Jenkins",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doctor_a = Doctor.objects.create(
            user=self.doctor_a_user,
            name="Sarah Jenkins",
            hospital=self.active_hospital,
            specialty="Cardiology",
            location="Oud Metha, Dubai",
            status=FacilityStatus.ACTIVE
        )

        # Doctor B @ Active Hospital
        self.doctor_b_user = User.objects.create_user(
            email="doc.mansoor@example.com",
            name="Tariq Al-Mansoor",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doctor_b = Doctor.objects.create(
            user=self.doctor_b_user,
            name="Tariq Al-Mansoor",
            hospital=self.active_hospital,
            specialty="Neurology",
            location="Oud Metha, Dubai",
            status=FacilityStatus.ACTIVE
        )

        # Doctor C @ Deactivated Hospital
        self.doctor_c_user = User.objects.create_user(
            email="doc.deactivated@example.com",
            name="Kareem Inactive",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doctor_c = Doctor.objects.create(
            user=self.doctor_c_user,
            name="Kareem Inactive",
            hospital=self.deactivated_hospital,
            specialty="General",
            status=FacilityStatus.ACTIVE
        )

        # 4. Patients
        # Patient 1 (Primary)
        self.patient_1 = User.objects.create_user(
            email="patient1@example.com",
            name="Patient One",
            password="StrongPassword2026!",
            role=UserRole.PATIENT,
            phone="+971501112233"
        )
        self.profile_1 = PatientProfile.objects.create(
            user=self.patient_1,
            dob=date(1990, 5, 20),
            gender="female",
            blood_group="A+"
        )
        self.dependent_1 = PatientDependent.objects.create(
            profile=self.profile_1,
            name="Little Timmy",
            relation="child",
            dob=date(2018, 1, 10),
            gender="male"
        )

        # Patient 2 (Unrelated)
        self.patient_2 = User.objects.create_user(
            email="patient2@example.com",
            name="Patient Two",
            password="StrongPassword2026!",
            role=UserRole.PATIENT,
            phone="+971502223344"
        )
        self.profile_2 = PatientProfile.objects.create(
            user=self.patient_2,
            dob=date(1985, 8, 15),
            gender="male",
            blood_group="O+"
        )

        # 5. Completed Appointment for Doctor A and Patient 1
        self.completed_appointment = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.profile_1,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=date.today(),
            time_slot="10:00 AM",
            status=AppointmentStatus.COMPLETED
        )

        # 6. Completed Appointment for Doctor A and Dependent 1
        self.dependent_appointment = Appointment.objects.create(
            booked_by=self.patient_1,
            dependent=self.dependent_1,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=date.today(),
            time_slot="11:00 AM",
            status=AppointmentStatus.COMPLETED
        )

        # 7. Incomplete Appointment (Confirmed status)
        self.incomplete_appointment = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.profile_1,
            doctor=self.doctor_a,
            hospital=self.active_hospital,
            date=date.today(),
            time_slot="02:00 PM",
            status=AppointmentStatus.CONFIRMED
        )

        # Standard payload
        self.valid_payload = {
            "appointment_id": str(self.completed_appointment.id),
            "diagnosis": "Hypertension Stage 1",
            "instructions": "Reduce dietary sodium intake and exercise 30 minutes daily.",
            "medications": [
                {
                    "medication_name": "Amlodipine",
                    "dosage": "5 mg",
                    "frequency": "Once daily in the morning",
                    "duration": "30 days",
                    "instructions": "Take with water"
                },
                {
                    "medication_name": "Lisinopril",
                    "dosage": "10 mg",
                    "frequency": "Once daily",
                    "duration": "30 days",
                    "instructions": "Monitor blood pressure"
                }
            ]
        }

    # =========================================================================
    # Group A: Creation
    # =========================================================================

    def test_01_doctor_can_create_for_own_completed_appointment(self):
        """Attending doctor successfully issues prescription for completed consultation."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('prescriptions:prescription-create')
        response = self.client.post(url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'active')
        self.assertEqual(response.data['diagnosis'], "Hypertension Stage 1")
        self.assertEqual(len(response.data['medications']), 2)
        self.assertEqual(response.data['patient_id'], str(self.patient_1.id))
        self.assertEqual(response.data['doctor_id'], str(self.doctor_a.id))
        self.assertFalse(response.data['is_dependent'])

        # Verify DB records
        prescription = Prescription.objects.get(id=response.data['id'])
        self.assertEqual(prescription.medications.count(), 2)

    def test_02_patient_cannot_create_prescription(self):
        """Patients are strictly forbidden from creating prescriptions (403 Forbidden)."""
        self.client.force_authenticate(user=self.patient_1)
        url = reverse('prescriptions:prescription-create')
        response = self.client.post(url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_03_unrelated_doctor_cannot_create_prescription(self):
        """Doctor B cannot issue prescription for Doctor A's appointment (404 Not Found)."""
        self.client.force_authenticate(user=self.doctor_b_user)
        url = reverse('prescriptions:prescription-create')
        response = self.client.post(url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_04_doctor_cannot_use_another_doctors_appointment(self):
        """Doctor cannot hijack another doctor's encounter ID (fails closed with 404)."""
        self.client.force_authenticate(user=self.doctor_b_user)
        url = reverse('prescriptions:prescription-create')
        response = self.client.post(url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Prescription.objects.count(), 0)

    def test_05_incomplete_appointment_rejected(self):
        """Prescriptions cannot be issued for appointments that are not completed (400 Bad Request)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        payload = dict(self.valid_payload)
        payload['appointment_id'] = str(self.incomplete_appointment.id)

        url = reverse('prescriptions:prescription-create')
        response = self.client.post(url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("completed", response.data['detail'])

    def test_06_duplicate_active_prescription_rejected(self):
        """Attempting to create a second active prescription for an appointment returns 409 Conflict."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('prescriptions:prescription-create')

        # First creation succeeds
        res1 = self.client.post(url, self.valid_payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Duplicate attempt fails with 409
        res2 = self.client.post(url, self.valid_payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("active prescription already exists", res2.data['detail'])

    # =========================================================================
    # Group B: Replacement Lifecycle
    # =========================================================================

    def test_07_issuing_doctor_can_cancel(self):
        """Issuing doctor can cancel their active prescription."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res_create = self.client.post(url_create, self.valid_payload, format='json')
        rx_id = res_create.data['id']

        # Cancel endpoint
        url_cancel = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id})
        res_cancel = self.client.post(url_cancel)

        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cancel.data['status'], 'cancelled')

        rx = Prescription.objects.get(id=rx_id)
        self.assertEqual(rx.status, PrescriptionStatus.CANCELLED)

    def test_08_non_issuing_doctor_cannot_cancel(self):
        """Another doctor cannot cancel someone else's prescription (404 Not Found)."""
        # Create by Doctor A
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res_create = self.client.post(url_create, self.valid_payload, format='json')
        rx_id = res_create.data['id']

        # Doctor B attempts cancellation
        self.client.force_authenticate(user=self.doctor_b_user)
        url_cancel = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id})
        res_cancel = self.client.post(url_cancel)

        self.assertEqual(res_cancel.status_code, status.HTTP_404_NOT_FOUND)

        rx = Prescription.objects.get(id=rx_id)
        self.assertEqual(rx.status, PrescriptionStatus.ACTIVE)

    def test_09_cancelled_prescription_remains_in_database(self):
        """Cancellation does NOT delete the record; historical record is preserved."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res_create = self.client.post(url_create, self.valid_payload, format='json')
        rx_id = res_create.data['id']

        url_cancel = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id})
        self.client.post(url_cancel)

        self.assertTrue(Prescription.objects.filter(id=rx_id).exists())
        self.assertEqual(PrescriptionMedication.objects.filter(prescription_id=rx_id).count(), 2)

    def test_10_cancelled_prescription_contents_remain_unchanged(self):
        """Clinical contents (diagnosis, instructions, medications) are identical post-cancellation."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res_create = self.client.post(url_create, self.valid_payload, format='json')
        rx_id = res_create.data['id']

        url_cancel = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id})
        self.client.post(url_cancel)

        rx = Prescription.objects.get(id=rx_id)
        self.assertEqual(rx.diagnosis, "Hypertension Stage 1")
        self.assertEqual(rx.instructions, "Reduce dietary sodium intake and exercise 30 minutes daily.")
        meds = list(rx.medications.order_by('medication_name').values_list('medication_name', flat=True))
        self.assertEqual(meds, ['Amlodipine', 'Lisinopril'])

    def test_11_replacement_can_be_created_after_cancellation(self):
        """After cancellation, the attending doctor can create a replacement prescription for the same appointment."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res_create1 = self.client.post(url_create, self.valid_payload, format='json')
        rx_id_1 = res_create1.data['id']

        # Cancel Rx 1
        url_cancel = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id_1})
        self.client.post(url_cancel)

        # Issue replacement prescription Rx 2
        replacement_payload = dict(self.valid_payload)
        replacement_payload['diagnosis'] = "Hypertension Stage 2 - Corrected"
        replacement_payload['medications'] = [
            {
                "medication_name": "Amlodipine",
                "dosage": "10 mg",
                "frequency": "Once daily",
                "duration": "60 days",
                "instructions": "Increased dose"
            }
        ]

        res_create2 = self.client.post(url_create, replacement_payload, format='json')
        self.assertEqual(res_create2.status_code, status.HTTP_201_CREATED)
        rx_id_2 = res_create2.data['id']

        self.assertNotEqual(rx_id_1, rx_id_2)
        self.assertEqual(res_create2.data['status'], 'active')
        self.assertEqual(res_create2.data['diagnosis'], "Hypertension Stage 2 - Corrected")

    def test_12_old_cancelled_prescription_and_new_active_coexist(self):
        """Both the old cancelled and new active prescription coexist linked to the same appointment."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res1 = self.client.post(url_create, self.valid_payload, format='json')
        rx_id_1 = res1.data['id']

        url_cancel = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id_1})
        self.client.post(url_cancel)

        replacement_payload = dict(self.valid_payload)
        replacement_payload['diagnosis'] = "Updated Diagnosis"
        res2 = self.client.post(url_create, replacement_payload, format='json')
        rx_id_2 = res2.data['id']

        appointment_rxs = self.completed_appointment.prescriptions.all()
        self.assertEqual(appointment_rxs.count(), 2)
        self.assertEqual(appointment_rxs.filter(status=PrescriptionStatus.CANCELLED).count(), 1)
        self.assertEqual(appointment_rxs.filter(status=PrescriptionStatus.ACTIVE).count(), 1)

    def test_13_second_active_prescription_is_rejected(self):
        """Cannot have two active prescriptions even when one cancelled prescription exists."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res1 = self.client.post(url_create, self.valid_payload, format='json')
        self.client.post(reverse('prescriptions:prescription-cancel', kwargs={'pk': res1.data['id']}))

        # Replacement creates active Rx 2
        res2 = self.client.post(url_create, self.valid_payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # Attempt to create active Rx 3 while Rx 2 is still active
        res3 = self.client.post(url_create, self.valid_payload, format='json')
        self.assertEqual(res3.status_code, status.HTTP_409_CONFLICT)

    def test_14_database_constraint_enforces_single_active_prescription(self):
        """Database constraint raises IntegrityError if attempting direct creation of 2 active prescriptions."""
        Prescription.objects.create(
            appointment=self.completed_appointment,
            doctor=self.doctor_a,
            patient=self.patient_1,
            diagnosis="Rx 1",
            status=PrescriptionStatus.ACTIVE
        )

        with self.assertRaises(IntegrityError):
            Prescription.objects.create(
                appointment=self.completed_appointment,
                doctor=self.doctor_a,
                patient=self.patient_1,
                diagnosis="Rx 2 Duplicate Active",
                status=PrescriptionStatus.ACTIVE
            )

    # =========================================================================
    # Group C: Access Control
    # =========================================================================

    def test_15_patient_can_read_own_prescription(self):
        """Patient account holder can read details of their prescription."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        self.client.force_authenticate(user=self.patient_1)
        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        response = self.client.get(url_detail)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], rx_id)
        self.assertEqual(len(response.data['medications']), 2)

    def test_16_unrelated_patient_gets_404(self):
        """Unrelated patient receives 404 Not Found (fail closed, no disclosure)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        self.client.force_authenticate(user=self.patient_2)
        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        response = self.client.get(url_detail)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_17_issuing_doctor_can_read_own_prescription(self):
        """Issuing doctor can retrieve their issued prescription."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        response = self.client.get(url_detail)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], rx_id)

    def test_18_unrelated_doctor_gets_404_unless_clinical_relationship_applies(self):
        """Unrelated doctor gets 404, but doctor with clinical encounter can read."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        # Doctor B has NO appointment with Patient 1 -> 404
        self.client.force_authenticate(user=self.doctor_b_user)
        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        res_no_rel = self.client.get(url_detail)
        self.assertEqual(res_no_rel.status_code, status.HTTP_404_NOT_FOUND)

        # Now Doctor B conducts an appointment with Patient 1 (confirmed)
        Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.profile_1,
            doctor=self.doctor_b,
            hospital=self.active_hospital,
            date=date.today(),
            time_slot="03:00 PM",
            status=AppointmentStatus.CONFIRMED
        )

        # Doctor B now has verified clinical relationship -> 200 OK
        res_with_rel = self.client.get(url_detail)
        self.assertEqual(res_with_rel.status_code, status.HTTP_200_OK)

    def test_19_facility_admin_cannot_read_phi(self):
        """Facility administrators receive 404 Not Found (administrative roles denied clinical PHI)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        self.client.force_authenticate(user=self.facility_admin_user)
        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        response = self.client.get(url_detail)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_20_platform_admin_cannot_read_phi(self):
        """Platform administrators receive 404 Not Found (clinical confidentiality)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        self.client.force_authenticate(user=self.platform_admin_user)
        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        response = self.client.get(url_detail)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_21_appointment_retrieval_properly_scoped(self):
        """Retrieving prescription by appointment ID respects authorization and returns active prescription."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        url_appt_rx = reverse('prescriptions:appointment-prescription', kwargs={'appointment_id': self.completed_appointment.id})

        # 1. Attending doctor accesses -> 200 OK
        res_doc = self.client.get(url_appt_rx)
        self.assertEqual(res_doc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_doc.data['id'], rx_id)

        # 2. Owning patient accesses -> 200 OK
        self.client.force_authenticate(user=self.patient_1)
        res_pat = self.client.get(url_appt_rx)
        self.assertEqual(res_pat.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pat.data['id'], rx_id)

        # 3. Unrelated patient accesses -> 404 Not Found
        self.client.force_authenticate(user=self.patient_2)
        res_unrel = self.client.get(url_appt_rx)
        self.assertEqual(res_unrel.status_code, status.HTTP_404_NOT_FOUND)

        # 4. If prescription is cancelled and no active Rx exists -> 404 Not Found
        self.client.force_authenticate(user=self.doctor_a_user)
        self.client.post(reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id}))

        res_cancelled = self.client.get(url_appt_rx)
        self.assertEqual(res_cancelled.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("No active prescription found", res_cancelled.data['detail'])

    # =========================================================================
    # Group D: Dependent Handling
    # =========================================================================

    def test_22_dependent_appointment_prescription_attributed_to_account_holder(self):
        """Prescription for dependent appointment is attributed to account holder with dependent details."""
        self.client.force_authenticate(user=self.doctor_a_user)
        payload = dict(self.valid_payload)
        payload['appointment_id'] = str(self.dependent_appointment.id)
        payload['diagnosis'] = "Pediatric Ear Infection"

        url = reverse('prescriptions:prescription-create')
        res = self.client.post(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['patient_id'], str(self.patient_1.id))
        self.assertTrue(res.data['is_dependent'])
        self.assertIsNotNone(res.data['dependent'])
        self.assertEqual(res.data['dependent']['name'], "Little Timmy")
        self.assertEqual(res.data['dependent']['relationship'], "child")

    def test_23_unauthorized_account_holder_cannot_access_dependent_prescription(self):
        """Another account holder cannot read the dependent's prescription (404 Not Found)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        payload = dict(self.valid_payload)
        payload['appointment_id'] = str(self.dependent_appointment.id)
        res = self.client.post(reverse('prescriptions:prescription-create'), payload, format='json')
        rx_id = res.data['id']

        self.client.force_authenticate(user=self.patient_2)
        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        response = self.client.get(url_detail)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # Group E: Integrity, Validation, Security & Immutability
    # =========================================================================

    def test_24_client_supplied_ids_cannot_override_server_derivation(self):
        """Rogue client cannot inject doctor_id, patient_id, or facility_id in payload."""
        self.client.force_authenticate(user=self.doctor_a_user)
        payload = dict(self.valid_payload)
        # Attempt to spoof doctor and patient
        payload['doctor_id'] = str(self.doctor_b.id)
        payload['patient_id'] = str(self.patient_2.id)
        payload['facility_id'] = str(self.deactivated_hospital.id)
        payload['status'] = 'dispensed'

        url = reverse('prescriptions:prescription-create')
        res = self.client.post(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Server must enforce Doctor A, Patient 1, and Active status
        self.assertEqual(res.data['doctor_id'], str(self.doctor_a.id))
        self.assertEqual(res.data['patient_id'], str(self.patient_1.id))
        self.assertEqual(res.data['status'], 'active')

    def test_25_doctor_at_deactivated_facility_cannot_prescribe(self):
        """Doctor affiliated with deactivated facility cannot issue prescriptions (403 Forbidden)."""
        # Create completed appointment for Doctor C at deactivated hospital
        appt_deactivated = Appointment.objects.create(
            booked_by=self.patient_1,
            patient_profile=self.profile_1,
            doctor=self.doctor_c,
            hospital=self.deactivated_hospital,
            date=date.today(),
            time_slot="12:00 PM",
            status=AppointmentStatus.COMPLETED
        )

        self.client.force_authenticate(user=self.doctor_c_user)
        payload = dict(self.valid_payload)
        payload['appointment_id'] = str(appt_deactivated.id)

        url = reverse('prescriptions:prescription-create')
        res = self.client.post(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("active facility", res.data['detail'])

    def test_26_audit_records_contain_no_clinical_phi(self):
        """Audit records for creation and cancellation contain operational metadata and ZERO clinical PHI."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url_create = reverse('prescriptions:prescription-create')
        res_create = self.client.post(url_create, self.valid_payload, format='json')
        rx_id = res_create.data['id']

        # Verify PRESCRIPTION_CREATED audit log
        audit_create = AuditLog.objects.filter(action='PRESCRIPTION_CREATED', target_id=rx_id).first()
        self.assertIsNotNone(audit_create)
        summary = audit_create.change_summary

        # Check required metadata
        self.assertIn('appointment_id', summary)
        self.assertIn('doctor_id', summary)
        self.assertIn('patient_id', summary)
        self.assertIn('medication_count', summary)

        # Crucial security assertion: NO clinical PHI in audit logs
        self.assertNotIn('diagnosis', summary)
        self.assertNotIn('medications', summary)
        self.assertNotIn('instructions', summary)
        summary_str = str(summary).lower()
        self.assertNotIn('hypertension', summary_str)
        self.assertNotIn('amlodipine', summary_str)
        self.assertNotIn('lisinopril', summary_str)

        # Cancel and verify PRESCRIPTION_CANCELLED audit log
        url_cancel = reverse('prescriptions:prescription-cancel', kwargs={'pk': rx_id})
        self.client.post(url_cancel)

        audit_cancel = AuditLog.objects.filter(action='PRESCRIPTION_CANCELLED', target_id=rx_id).first()
        self.assertIsNotNone(audit_cancel)
        cancel_summary = audit_cancel.change_summary
        self.assertEqual(cancel_summary['status'], 'cancelled')
        cancel_str = str(cancel_summary).lower()
        self.assertNotIn('hypertension', cancel_str)
        self.assertNotIn('amlodipine', cancel_str)

    def test_27_medication_validation_works(self):
        """Medication items must be non-empty and have valid required fields (400 Bad Request)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse('prescriptions:prescription-create')

        # 1. Empty medication list
        payload1 = dict(self.valid_payload)
        payload1['medications'] = []
        res1 = self.client.post(url, payload1, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Missing dosage
        payload2 = dict(self.valid_payload)
        payload2['medications'] = [{
            "medication_name": "Paracetamol",
            "dosage": "",
            "frequency": "Twice daily",
            "duration": "5 days"
        }]
        res2 = self.client.post(url, payload2, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_28_immutable_prescription_contents_cannot_be_modified(self):
        """Generic PUT and PATCH on prescription detail are forbidden (405 Method Not Allowed)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        url_detail = reverse('prescriptions:prescription-detail', kwargs={'pk': rx_id})
        res_put = self.client.put(url_detail, {"diagnosis": "Tampered Diagnosis"}, format='json')
        self.assertEqual(res_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_patch = self.client.patch(url_detail, {"diagnosis": "Tampered Diagnosis"}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_29_my_prescriptions_scoped_for_patient_and_doctor(self):
        """GET /api/v1/prescriptions/my/ correctly scopes results by caller role."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(reverse('prescriptions:prescription-create'), self.valid_payload, format='json')
        rx_id = res.data['id']

        url_my = reverse('prescriptions:prescription-my-list')

        # 1. Patient sees their prescription
        self.client.force_authenticate(user=self.patient_1)
        res_pat = self.client.get(url_my)
        self.assertEqual(res_pat.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_pat.data), 1)
        self.assertEqual(res_pat.data[0]['id'], rx_id)

        # 2. Patient 2 sees zero prescriptions
        self.client.force_authenticate(user=self.patient_2)
        res_pat2 = self.client.get(url_my)
        self.assertEqual(res_pat2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_pat2.data), 0)

        # 3. Doctor A sees the issued prescription
        self.client.force_authenticate(user=self.doctor_a_user)
        res_doc_a = self.client.get(url_my)
        self.assertEqual(res_doc_a.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_doc_a.data), 1)

        # 4. Doctor B sees zero prescriptions
        self.client.force_authenticate(user=self.doctor_b_user)
        res_doc_b = self.client.get(url_my)
        self.assertEqual(res_doc_b.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_doc_b.data), 0)

        # 5. Facility admin receives 403 Forbidden
        self.client.force_authenticate(user=self.facility_admin_user)
        res_admin = self.client.get(url_my)
        self.assertEqual(res_admin.status_code, status.HTTP_403_FORBIDDEN)
