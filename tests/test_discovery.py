"""Automated Test Suite for Phase 4 Public Healthcare Discovery Services."""
from datetime import date
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserRole, PatientProfile
from apps.facilities.models import Hospital, Clinic, FacilityDepartment, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule
from apps.appointments.models import Appointment, AppointmentStatus

class PublicDiscoveryTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Hospitals (One active, one deactivated)
        self.active_hospital = Hospital.objects.create(
            name="American Hospital Dubai",
            name_ar="المستشفى الأمريكي دبي",
            location="Oud Metha, Dubai",
            address="19th St, Oud Metha",
            phone="+97143775500",
            operating_hours="24/7",
            about="Premier tertiary healthcare center.",
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
        self.dept_cardio = FacilityDepartment.objects.create(
            hospital=self.active_hospital,
            name="Cardiology Department",
            head_of_department="Dr. Heart",
            bed_capacity=45
        )
        self.deactivated_hospital = Hospital.objects.create(
            name="Old Closed Hospital",
            location="Deira, Dubai",
            address="Deira St",
            phone="+97140000000",
            operating_hours="Closed",
            about="Decommissioned facility.",
            emergency_available=False,
            status=FacilityStatus.DEACTIVATED
        )

        # 2. Clinics (One active dental clinic)
        self.active_clinic = Clinic.objects.create(
            name="Prime Dental Care Clinic",
            name_ar="عيادة برايم لطب الأسنان",
            location="Jumeirah, Dubai",
            address="Jumeirah Beach Road",
            primary_specialty="Dental",
            phone="+97143441122",
            operating_hours="09:00 - 20:00",
            about="Specialized aesthetic and orthodontic dental clinic.",
            status=FacilityStatus.ACTIVE
        )

        # 3. Doctors
        # Doctor A: Active Cardiologist @ American Hospital
        self.user_doc_a = User.objects.create_user(
            email="doc.cardio@example.com",
            name="Dr. Sarah Jenkins",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doc_a = Doctor.objects.create(
            user=self.user_doc_a,
            name="Dr. Sarah Jenkins",
            name_ar="د. سارة جنكينز",
            hospital=self.active_hospital,
            specialty="Cardiology",
            special_interests=["Echocardiography", "Preventive Cardiology"],
            experience_years=14,
            location="Oud Metha, Dubai",
            consultation_fee=400.00,
            rating=4.9,
            review_count=82,
            status=FacilityStatus.ACTIVE
        )
        # Schedule for Doctor A: Practices Mondays & Wednesdays
        self.schedule_a = DoctorSchedule.objects.create(
            doctor=self.doc_a,
            available_days=["Monday", "Wednesday"],
            standard_slots=["09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM"],
            slot_duration_minutes=30
        )

        # Doctor B: Active Dentist @ Prime Dental Clinic
        self.user_doc_b = User.objects.create_user(
            email="doc.dentist@example.com",
            name="Dr. Kareem Zaid",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doc_b = Doctor.objects.create(
            user=self.user_doc_b,
            name="Dr. Kareem Zaid",
            clinic=self.active_clinic,
            specialty="Dental",
            experience_years=8,
            location="Jumeirah, Dubai",
            consultation_fee=250.00,
            rating=4.7,
            review_count=35,
            status=FacilityStatus.ACTIVE
        )

        # Doctor C: Deactivated Doctor
        self.user_doc_c = User.objects.create_user(
            email="doc.inactive@example.com",
            name="Dr. Inactive Person",
            password="StrongPassword2026!",
            role=UserRole.DOCTOR
        )
        self.doc_c = Doctor.objects.create(
            user=self.user_doc_c,
            name="Dr. Inactive Person",
            hospital=self.active_hospital,
            specialty="Dermatology",
            location="Dubai",
            status=FacilityStatus.DEACTIVATED
        )

        # Deactivated Clinic & Doctors attached to deactivated facilities (Fix 1 & 2 tests)
        self.deactivated_clinic = Clinic.objects.create(
            name="Old Decommissioned Clinic",
            location="Deira, Dubai",
            address="Deira Clinic St",
            primary_specialty="Ophthalmology",
            phone="+97140000001",
            operating_hours="Closed",
            about="Closed clinic facility.",
            status=FacilityStatus.DEACTIVATED
        )
        # Doctor in deactivated hospital (Active doctor, but Hospital is Deactivated)
        self.doc_in_deactivated_hosp = Doctor.objects.create(
            name="Dr. Deactivated Hosp Specialist",
            hospital=self.deactivated_hospital,
            specialty="Neurosurgery",
            location="Deira",
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.doc_in_deactivated_hosp,
            available_days=["Monday"],
            standard_slots=["09:00 AM", "09:30 AM"]
        )

        # Doctor in deactivated clinic (Active doctor, but Clinic is Deactivated)
        self.doc_in_deactivated_clinic = Doctor.objects.create(
            name="Dr. Deactivated Clinic Specialist",
            clinic=self.deactivated_clinic,
            specialty="Ophthalmology",
            location="Deira",
            status=FacilityStatus.ACTIVE
        )
        DoctorSchedule.objects.create(
            doctor=self.doc_in_deactivated_clinic,
            available_days=["Monday"],
            standard_slots=["09:00 AM", "09:30 AM"]
        )

        # Patient for appointment booking tests
        self.patient_user = User.objects.create_user(
            email="patient.test@example.com",
            name="Patient Test",
            password="StrongPassword2026!",
            role=UserRole.PATIENT
        )
        self.patient_profile = PatientProfile.objects.create(user=self.patient_user)

    def _results(self, data):
        if isinstance(data, list):
            return data
        return data.get('results', [])

    def test_doctor_directory_list_and_public_fields(self):
        """Doctor directory returns active doctors with public fields and without sensitive credentials."""
        response = self.client.get(reverse('doctors:doctor_list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        docs = self._results(response.data)
        doc_names = [d['name'] for d in docs]

        self.assertIn("Dr. Sarah Jenkins", doc_names)
        self.assertIn("Dr. Kareem Zaid", doc_names)
        # Deactivated doctor C must NOT be returned
        self.assertNotIn("Dr. Inactive Person", doc_names)

        # Verify no sensitive fields leaked
        first_doc = docs[0]
        self.assertNotIn('password', first_doc)
        self.assertNotIn('is_staff', first_doc)
        self.assertNotIn('is_superuser', first_doc)

    def test_doctor_faceted_filtering(self):
        """Faceted filtering by specialty, location, rating, and keyword."""
        # 1. Filter by specialty
        res_cardio = self.client.get(reverse('doctors:doctor_list'), {'specialty': 'Cardiology'})
        docs_cardio = self._results(res_cardio.data)
        self.assertEqual(len(docs_cardio), 1)
        self.assertEqual(docs_cardio[0]['name'], "Dr. Sarah Jenkins")

        # 2. Filter by location
        res_loc = self.client.get(reverse('doctors:doctor_list'), {'location': 'Jumeirah'})
        docs_loc = self._results(res_loc.data)
        self.assertEqual(len(docs_loc), 1)
        self.assertEqual(docs_loc[0]['name'], "Dr. Kareem Zaid")

        # 3. Filter by hospital
        res_hosp = self.client.get(reverse('doctors:doctor_list'), {'hospital': str(self.active_hospital.id)})
        docs_hosp = self._results(res_hosp.data)
        self.assertEqual(len(docs_hosp), 1)
        self.assertEqual(docs_hosp[0]['name'], "Dr. Sarah Jenkins")

        # 4. Filter by minimum rating
        res_rating = self.client.get(reverse('doctors:doctor_list'), {'min_rating': '4.8'})
        docs_rating = self._results(res_rating.data)
        self.assertEqual(len(docs_rating), 1)
        self.assertEqual(docs_rating[0]['name'], "Dr. Sarah Jenkins")

        # 5. Filter by practicing day (Doctor A practices on Monday)
        res_day = self.client.get(reverse('doctors:doctor_list'), {'day': 'Monday'})
        docs_day = self._results(res_day.data)
        self.assertEqual(len(docs_day), 1)
        self.assertEqual(docs_day[0]['name'], "Dr. Sarah Jenkins")

        # 6. Keyword search across name or specialty
        res_search = self.client.get(reverse('doctors:doctor_list'), {'search': 'Jenkins'})
        docs_search = self._results(res_search.data)
        self.assertEqual(len(docs_search), 1)
        self.assertEqual(docs_search[0]['name'], "Dr. Sarah Jenkins")

    def test_doctor_detail_and_deactivated_exclusion(self):
        """Doctor detail returns full schedule and facility info; deactivated doctors return 404."""
        # Active doctor detail -> 200 OK
        res = self.client.get(reverse('doctors:doctor_detail', kwargs={'pk': self.doc_a.id}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['name'], "Dr. Sarah Jenkins")
        self.assertEqual(res.data['facility_details']['type'], 'hospital')
        self.assertIn("Monday", res.data['schedule']['available_days'])

        # Deactivated doctor detail -> 404 Not Found
        res_inactive = self.client.get(reverse('doctors:doctor_detail', kwargs={'pk': self.doc_c.id}))
        self.assertEqual(res_inactive.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_availability_calculation(self):
        """Availability endpoint calculates available slots and excludes existing active bookings."""
        # 2026-10-05 is a Monday (Doctor A practices on Monday)
        monday_date = date(2026, 10, 5)
        # 2026-10-06 is a Tuesday (Doctor A does NOT practice on Tuesday)
        tuesday_date = date(2026, 10, 6)

        url = reverse('doctors:doctor_availability', kwargs={'pk': self.doc_a.id})

        # 1. Non-practicing day returns available=False
        res_tue = self.client.get(url, {'date': str(tuesday_date)})
        self.assertEqual(res_tue.status_code, status.HTTP_200_OK)
        self.assertFalse(res_tue.data['available'])
        self.assertEqual(len(res_tue.data['slots']), 0)

        # 2. Practicing day with no bookings -> all 4 standard slots available
        res_mon = self.client.get(url, {'date': str(monday_date)})
        self.assertEqual(res_mon.status_code, status.HTTP_200_OK)
        self.assertTrue(res_mon.data['available'])
        self.assertEqual(len(res_mon.data['slots']), 4)
        self.assertIn("09:30 AM", res_mon.data['slots'])

        # 3. Create a confirmed booking for 09:30 AM
        Appointment.objects.create(
            doctor=self.doc_a,
            hospital=self.active_hospital,
            patient_profile=self.patient_profile,
            booked_by=self.patient_user,
            patient_name_snapshot="Jane Doe",
            specialty_snapshot="Cardiology",
            date=monday_date,
            time_slot="09:30 AM",
            status=AppointmentStatus.CONFIRMED
        )

        res_mon_booked = self.client.get(url, {'date': str(monday_date)})
        self.assertEqual(res_mon_booked.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_mon_booked.data['slots']), 3)
        self.assertNotIn("09:30 AM", res_mon_booked.data['slots'])
        self.assertIn("09:30 AM", res_mon_booked.data['booked_slots'])

        # 4. Cancel the appointment -> slot becomes available again
        apt = Appointment.objects.get(doctor=self.doc_a, date=monday_date, time_slot="09:30 AM")
        apt.status = AppointmentStatus.CANCELLED
        apt.save()

        res_mon_freed = self.client.get(url, {'date': str(monday_date)})
        self.assertEqual(len(res_mon_freed.data['slots']), 4)
        self.assertIn("09:30 AM", res_mon_freed.data['slots'])

        # 5. Fix 1: Availability for doctor attached to deactivated hospital -> 404
        url_deact_hosp = reverse('doctors:doctor_availability', kwargs={'pk': self.doc_in_deactivated_hosp.id})
        res_deact_hosp = self.client.get(url_deact_hosp, {'date': str(monday_date)})
        self.assertEqual(res_deact_hosp.status_code, status.HTTP_404_NOT_FOUND)

        # 6. Fix 1: Availability for doctor attached to deactivated clinic -> 404
        url_deact_clinic = reverse('doctors:doctor_availability', kwargs={'pk': self.doc_in_deactivated_clinic.id})
        res_deact_clinic = self.client.get(url_deact_clinic, {'date': str(monday_date)})
        self.assertEqual(res_deact_clinic.status_code, status.HTTP_404_NOT_FOUND)

        # 7. Availability for deactivated doctor -> 404
        url_inactive_doc = reverse('doctors:doctor_availability', kwargs={'pk': self.doc_c.id})
        res_inactive_doc = self.client.get(url_inactive_doc, {'date': str(monday_date)})
        self.assertEqual(res_inactive_doc.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_uuid_query_parameters(self):
        """Fix 3: Doctor directory handles malformed UUID query parameters gracefully with 200 OK and empty list."""
        # Invalid hospital UUID
        res_hosp = self.client.get(reverse('doctors:doctor_list'), {'hospital': 'not-a-uuid'})
        self.assertEqual(res_hosp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._results(res_hosp.data)), 0)

        res_hosp_id = self.client.get(reverse('doctors:doctor_list'), {'hospital_id': 'invalid-uuid-format-123'})
        self.assertEqual(res_hosp_id.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._results(res_hosp_id.data)), 0)

        # Invalid clinic UUID
        res_clinic = self.client.get(reverse('doctors:doctor_list'), {'clinic': 'bad-clinic-uuid'})
        self.assertEqual(res_clinic.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._results(res_clinic.data)), 0)

        res_clinic_id = self.client.get(reverse('doctors:doctor_list'), {'clinic_id': 'definitely-not-uuid'})
        self.assertEqual(res_clinic_id.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._results(res_clinic_id.data)), 0)

    def test_hospital_list_and_detail_views(self):
        """Hospital list filters active facilities and detail returns departments and affiliated doctors."""
        # 1. Hospital list
        res_list = self.client.get(reverse('facilities:hospital_list'))
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        hospitals = self._results(res_list.data)
        names = [h['name'] for h in hospitals]
        self.assertIn("American Hospital Dubai", names)
        # Deactivated hospital must NOT be listed
        self.assertNotIn("Old Closed Hospital", names)

        # Verify doctor count & specialties on hospital
        target = [h for h in hospitals if h['name'] == "American Hospital Dubai"][0]
        self.assertEqual(target['doctor_count'], 1)
        self.assertIn("Cardiology", target['specialties'])

        # 2. Emergency filter
        res_emg = self.client.get(reverse('facilities:hospital_list'), {'emergency_available': 'true'})
        emg_hospitals = self._results(res_emg.data)
        self.assertTrue(all(h['emergency_available'] for h in emg_hospitals))

        # 3. Hospital detail view
        res_detail = self.client.get(reverse('facilities:hospital_detail', kwargs={'pk': self.active_hospital.id}))
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_detail.data['departments']), 1)
        self.assertEqual(res_detail.data['departments'][0]['name'], "Cardiology Department")
        self.assertEqual(len(res_detail.data['doctors']), 1)
        self.assertEqual(res_detail.data['doctors'][0]['name'], "Dr. Sarah Jenkins")

        # 4. Deactivated hospital detail -> 404
        res_inactive = self.client.get(reverse('facilities:hospital_detail', kwargs={'pk': self.deactivated_hospital.id}))
        self.assertEqual(res_inactive.status_code, status.HTTP_404_NOT_FOUND)

    def test_clinic_list_and_detail_views(self):
        """Clinic list filters active clinics and detail returns affiliated doctors."""
        # 1. Clinic list
        res_list = self.client.get(reverse('facilities:clinic_list'))
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        clinics = self._results(res_list.data)
        names = [c['name'] for c in clinics]
        self.assertIn("Prime Dental Care Clinic", names)

        # 2. Specialty filter
        res_spec = self.client.get(reverse('facilities:clinic_list'), {'specialty': 'Dental'})
        self.assertEqual(len(self._results(res_spec.data)), 1)

        # 3. Clinic detail
        res_detail = self.client.get(reverse('facilities:clinic_detail', kwargs={'pk': self.active_clinic.id}))
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['primary_specialty'], "Dental")
        self.assertEqual(len(res_detail.data['doctors']), 1)
        self.assertEqual(res_detail.data['doctors'][0]['name'], "Dr. Kareem Zaid")

    def test_hospital_and_clinic_annotated_doctor_count(self):
        """Fix 4: Verify doctor counts are accurately annotated and specialties are serialized efficiently."""
        # 1. Hospital list has annotated doctor_count and specialties from active doctors
        res_hosp_list = self.client.get(reverse('facilities:hospital_list'))
        self.assertEqual(res_hosp_list.status_code, status.HTTP_200_OK)
        hospitals = self._results(res_hosp_list.data)
        active_hosp = [h for h in hospitals if h['id'] == str(self.active_hospital.id)][0]
        # Active doctor A is counted, inactive doc C is NOT counted
        self.assertEqual(active_hosp['doctor_count'], 1)
        self.assertEqual(active_hosp['specialties'], ['Cardiology'])

        # 2. Clinic list has annotated doctor_count
        res_clinic_list = self.client.get(reverse('facilities:clinic_list'))
        self.assertEqual(res_clinic_list.status_code, status.HTTP_200_OK)
        clinics = self._results(res_clinic_list.data)
        active_cln = [c for c in clinics if c['id'] == str(self.active_clinic.id)][0]
        self.assertEqual(active_cln['doctor_count'], 1)

    def test_specialties_list(self):
        """Fix 2: Specialties list returns distinct active medical specialties from active facilities only."""
        response = self.client.get(reverse('facilities:specialty_list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        specialties = response.data.get('specialties', [])
        # Active doctor in active hospital
        self.assertIn("Cardiology", specialties)
        # Active clinic
        self.assertIn("Dental", specialties)

        # Fix 2: Specialties exclusive to deactivated facilities MUST NOT appear
        # Doctor in deactivated hospital has Neurosurgery
        self.assertNotIn("Neurosurgery", specialties)
        # Doctor in deactivated clinic has Ophthalmology
        self.assertNotIn("Ophthalmology", specialties)
        # Inactive doctor has Dermatology
        self.assertNotIn("Dermatology", specialties)

    def test_health_conditions_directory(self):
        """Fix 5: A-Z Health conditions index and detail retrieval with camelCase contract fields."""
        # 1. Condition list
        res_list = self.client.get(reverse('facilities:condition_list'))
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertIn('letters', res_list.data)
        self.assertIn('A', res_list.data['letters'])
        self.assertGreater(res_list.data['count'], 0)

        # Verify camelCase aliases in list items
        first_item = res_list.data['results'][0]
        self.assertIn('specialtyQuery', first_item)
        self.assertEqual(first_item['specialtyQuery'], first_item['specialty'])
        self.assertIn('riskFactors', first_item)
        self.assertEqual(first_item['riskFactors'], first_item['risk_factors'])

        # 2. Filter by letter
        res_letter = self.client.get(reverse('facilities:condition_list'), {'letter': 'A'})
        self.assertEqual(res_letter.status_code, status.HTTP_200_OK)
        for item in res_letter.data['results']:
            self.assertEqual(item['letter'], 'A')

        # 3. Search condition by symptom/keyword
        res_search = self.client.get(reverse('facilities:condition_list'), {'search': 'Asthma'})
        self.assertEqual(res_search.status_code, status.HTTP_200_OK)
        self.assertGreater(len(res_search.data['results']), 0)
        names = [c['name'] for c in res_search.data['results']]
        self.assertIn("Allergies & Asthma", names)

        # 4. Detail view
        res_detail = self.client.get(reverse('facilities:condition_detail', kwargs={'condition_id': 'allergies-asthma'}))
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['name'], "Allergies & Asthma")
        self.assertEqual(res_detail.data['specialty'], "Pulmonology")
        self.assertEqual(res_detail.data['specialtyQuery'], "Pulmonology")
        self.assertIn('riskFactors', res_detail.data)
        self.assertEqual(res_detail.data['riskFactors'], res_detail.data['risk_factors'])

        # 5. Non-existent condition -> 404
        res_404 = self.client.get(reverse('facilities:condition_detail', kwargs={'condition_id': 'unknown-condition-xyz'}))
        self.assertEqual(res_404.status_code, status.HTTP_404_NOT_FOUND)
