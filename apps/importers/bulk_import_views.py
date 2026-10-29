"""Excel & CSV Bulk Importers for Doctors and Facilities."""
import os
import io
import re
import csv
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse, FileResponse
from rest_framework import views, status, permissions
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError, PermissionDenied

from apps.accounts.permissions import IsPlatformAdmin, IsFacilityAdmin
from apps.accounts.models import User, UserRole
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.facilities.facility_views import get_facility_for_user
from apps.doctors.models import Doctor, DoctorSchedule
from apps.audit.utils import log_audit_event


def parse_xlsx_cells(content_bytes):
    """Zero-dependency parser for .xlsx XML cells."""
    with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            sroot = ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared_strings = [
                ''.join(elem.itertext())
                for elem in sroot.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si')
            ]

        sheet_name = 'xl/worksheets/sheet1.xml'
        root = ET.fromstring(z.read(sheet_name))

        rows = {}
        for c in root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
            cell_ref = c.get('r')
            if not cell_ref:
                continue
            m = re.match(r'([A-Z]+)([0-9]+)', cell_ref)
            if not m:
                continue
            col_letters, row_num = m.groups()
            row_idx = int(row_num)
            col_idx = 0
            for char in col_letters:
                col_idx = col_idx * 26 + (ord(char) - ord('A') + 1)
            col_idx -= 1
            v = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
            t = c.get('t')
            val = ''
            if v is not None and v.text is not None:
                if t == 's':
                    val = shared_strings[int(v.text)]
                else:
                    val = v.text
            if row_idx not in rows:
                rows[row_idx] = {}
            rows[row_idx][col_idx] = val.strip()

        max_row = max(rows.keys()) if rows else 0
        matrix = []
        for r in range(1, max_row + 1):
            if r in rows:
                max_col = max(rows[r].keys()) if rows[r] else 0
                r_cells = [rows[r].get(c, '') for c in range(max_col + 1)]
                matrix.append(r_cells)
            else:
                matrix.append([])
        return matrix


def parse_csv_cells(content_bytes):
    """Parse CSV content bytes with UTF-8 / UTF-8-sig."""
    decoded = content_bytes.decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(decoded))
    return [row for row in reader]


def normalize_key(k):
    return re.sub(r'[^a-z0-9]', '', str(k).lower())


def extract_records(matrix):
    """Detect orientation (transposed vs standard table) and extract records as list of dicts."""
    clean_matrix = []
    for row in matrix:
        while row and not row[0]:
            row = row[1:]
        if any(row):
            clean_matrix.append(row)
    if not clean_matrix:
        return []

    first_col = [row[0] for row in clean_matrix if row]
    norm_first_col = [normalize_key(x) for x in first_col]

    doctor_signals = {'hospitalname', 'firstname', 'lastname', 'speciality', 'department'}
    hospital_signals = {'hospitalname', 'country', 'emiratesprovince', 'area'}

    is_transposed = len(set(norm_first_col) & (doctor_signals | hospital_signals)) >= 2

    records = []
    if is_transposed:
        max_cols = max(len(row) for row in clean_matrix)
        for c in range(1, max_cols):
            rec = {}
            has_val = False
            for row in clean_matrix:
                header = row[0]
                val = row[c] if c < len(row) else ''
                if val:
                    has_val = True
                rec[normalize_key(header)] = val
            if has_val:
                records.append(rec)
    else:
        headers = [normalize_key(h) for h in clean_matrix[0]]
        for row in clean_matrix[1:]:
            rec = {}
            has_val = False
            for idx, h in enumerate(headers):
                val = row[idx] if idx < len(row) else ''
                if val:
                    has_val = True
                rec[h] = val
            if has_val:
                records.append(rec)

    # Filter out pure template guidance/notes columns
    filtered = []
    for r in records:
        f_name = r.get('firstname', '').lower()
        if f_name in ['entry manual', 'manual', 'notes', 'example notes']:
            continue
        h_name = r.get('hospitalname', '').lower()
        if h_name in ['entry manual', 'manual', 'notes']:
            continue
        filtered.append(r)
    return filtered


class AdminBulkImportDoctorsView(views.APIView):
    """
    Bulk import doctors from Excel (.xlsx) or CSV (.csv).
    POST /api/v1/admin/import/doctors/
    """
    permission_classes = [IsPlatformAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            raise ValidationError({'file': 'Please upload an .xlsx or .csv file.'})

        fname = uploaded_file.name.lower()
        content = uploaded_file.read()

        try:
            if fname.endswith('.xlsx'):
                matrix = parse_xlsx_cells(content)
            elif fname.endswith('.csv'):
                matrix = parse_csv_cells(content)
            else:
                raise ValidationError({'file': 'Only .xlsx and .csv file formats are supported.'})
        except Exception as e:
            return Response({'error': f'Failed to parse file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        records = extract_records(matrix)
        if not records:
            return Response({'error': 'No data records found in file.'}, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        errors = []
        created_doctors = []

        all_hospitals = {h.name.lower(): h for h in Hospital.objects.all()}
        all_clinics = {c.name.lower(): c for c in Clinic.objects.all()}

        for idx, rec in enumerate(records, 1):
            first_name = rec.get('firstname', '').strip()
            last_name = rec.get('lastname', '').strip()

            if not first_name and not last_name:
                continue

            full_name = f"Dr. {first_name} {last_name}".strip()
            if not full_name or full_name == 'Dr.':
                full_name = rec.get('doctorfullname', '').strip() or 'Dr. Specialist'

            hosp_name = rec.get('hospitalname', '').strip()
            facility_hospital = None
            facility_clinic = None

            if hosp_name:
                h_lower = hosp_name.lower()
                for name_k, h in all_hospitals.items():
                    if h_lower in name_k or name_k in h_lower:
                        facility_hospital = h
                        break
                if not facility_hospital:
                    for name_k, c in all_clinics.items():
                        if h_lower in name_k or name_k in h_lower:
                            facility_clinic = c
                            break

            dept = rec.get('department', '').strip()
            gender = rec.get('gender', 'Male').strip().capitalize()
            if gender not in ['Male', 'Female', 'Other']:
                gender = 'Male'

            quals_raw = rec.get('qualifications', '').strip()
            qualifications = [q.strip() for q in quals_raw.split(',') if q.strip()]

            specialty = rec.get('speciality', '').strip() or rec.get('specialty', '').strip() or 'General Medicine'

            interests_raw = rec.get('specialintrests', '').strip() or rec.get('specialinterests', '').strip()
            special_interests = [s.strip() for s in interests_raw.split(',') if s.strip()]

            exp_raw = rec.get('yearsofexperience', '').strip()
            exp_num = 5
            if exp_raw:
                digits = re.findall(r'\d+', exp_raw)
                if digits:
                    try:
                        exp_num = int(digits[0])
                    except:
                        exp_num = 5

            country_origin = rec.get('countryoforigin', '').strip() or 'United Arab Emirates'

            langs_raw = rec.get('languagespoken', '').strip() or rec.get('languages', '').strip()
            languages = [l.strip() for l in langs_raw.split(',') if l.strip()] or ['English', 'Arabic']

            dial_code = rec.get('clinicdialcode', '').strip() or rec.get('countrycodearea971uae', '').strip() or '+971'
            if not dial_code.startswith('+') or len(dial_code) > 16:
                dial_code = '+971'
            contact_number = rec.get('contactnumber', '').strip()
            email = rec.get('email', '').strip()
            about = rec.get('doctorprofile', '').strip() or f"{full_name} is an accredited medical specialist."
            photo = rec.get('doctorimagefilename', '').strip() or rec.get('photo', '').strip()

            username = rec.get('username', '').strip() or email or f"doc_{first_name.lower()}_{idx}"
            password = rec.get('password', '').strip() or 'Doctor@12345'

            try:
                # User account
                user = None
                user_email = email or (username if '@' in username else f"{username}@meetadr.local")
                if user_email:
                    if not User.objects.filter(email=user_email).exists():
                        user = User.objects.create_user(
                            email=user_email,
                            password=password,
                            role=UserRole.DOCTOR,
                            name=full_name,
                        )

                doc = Doctor.objects.create(
                    user=user,
                    name=full_name,
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    department=dept,
                    qualifications=qualifications,
                    specialty=specialty,
                    special_interests=special_interests,
                    experience_years=exp_num,
                    country_of_origin=country_origin,
                    languages=languages,
                    phone_dial_code=dial_code,
                    contact_number=contact_number,
                    email=email,
                    about=about,
                    photo=photo,
                    hospital=facility_hospital,
                    clinic=facility_clinic,
                    location=facility_hospital.location if facility_hospital else (facility_clinic.location if facility_clinic else 'Dubai'),
                    consultation_fee=Decimal('350.00'),
                    status=FacilityStatus.ACTIVE,
                )

                # Initialize schedule
                DoctorSchedule.objects.create(
                    doctor=doc,
                    available_days=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                    standard_slots=['09:00', '10:00', '11:00', '14:00', '15:00', '16:00'],
                )

                created_count += 1
                created_doctors.append({'id': str(doc.id), 'name': doc.name, 'specialty': doc.specialty})
            except Exception as e:
                errors.append({'record': idx, 'name': full_name, 'error': str(e)})

        log_audit_event(
            action="BULK_IMPORT_DOCTORS",
            target_model="Doctor",
            target_id="bulk",
            actor=request.user,
            change_summary={"total": len(records), "imported": created_count, "errors": len(errors)},
            request=request
        )

        return Response({
            'success': True,
            'total_records': len(records),
            'imported': created_count,
            'errors': errors,
            'doctors': created_doctors,
        }, status=status.HTTP_201_CREATED if created_count > 0 else status.HTTP_400_BAD_REQUEST)


class AdminBulkImportHospitalsView(views.APIView):
    """
    Bulk import hospitals/clinics from Excel (.xlsx) or CSV (.csv).
    POST /api/v1/admin/import/hospitals/
    """
    permission_classes = [IsPlatformAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            raise ValidationError({'file': 'Please upload an .xlsx or .csv file.'})

        fname = uploaded_file.name.lower()
        content = uploaded_file.read()

        try:
            if fname.endswith('.xlsx'):
                matrix = parse_xlsx_cells(content)
            elif fname.endswith('.csv'):
                matrix = parse_csv_cells(content)
            else:
                raise ValidationError({'file': 'Only .xlsx and .csv file formats are supported.'})
        except Exception as e:
            return Response({'error': f'Failed to parse file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        records = extract_records(matrix)
        if not records:
            return Response({'error': 'No data records found in file.'}, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        errors = []
        created_facilities = []

        for idx, rec in enumerate(records, 1):
            h_name = rec.get('hospitalname', '').strip()
            if not h_name:
                continue

            category_raw = rec.get('hospitalclinicwellness', '').strip() or 'Hospital'
            cat_norm = category_raw.capitalize()
            if cat_norm not in ['Hospital', 'Clinic', 'Wellness']:
                cat_norm = 'Hospital'

            is_clinic = cat_norm == 'Clinic'
            country = rec.get('country', '').strip() or 'United Arab Emirates'
            emirate = rec.get('emiratesprovince', '').strip() or 'Dubai'
            area = rec.get('area', '').strip()
            address = rec.get('addressoforganization', '').strip() or f"{emirate}, UAE"

            lat_val = rec.get('latitude', '').strip()
            lng_val = rec.get('longitude', '').strip()
            lat = None
            lng = None
            try:
                if lat_val:
                    lat = Decimal(str(float(lat_val)))
            except:
                pass
            try:
                if lng_val:
                    lng = Decimal(str(float(lng_val)))
            except:
                pass

            dial_code = rec.get('countrydialcode', '').strip() or rec.get('countrycodearea971uae', '').strip() or '+971'
            main_phone = rec.get('hospitalmainnumber', '').strip() or '+971 4 000 0000'
            website = rec.get('website', '').strip()
            about = rec.get('hospitalprofile', '').strip() or f"{h_name} is an accredited healthcare facility in {emirate}."
            photo = rec.get('hospitalimage', '').strip()
            logo = rec.get('hospitallogo', '').strip()
            ins_raw = (
                rec.get('insurance', '').strip()
                or rec.get('insurances', '').strip()
                or rec.get('acceptedinsurances', '').strip()
                or rec.get('insuranceplans', '').strip()
                or rec.get('acceptedinsurance', '').strip()
            )

            mgr_name = rec.get('managername', '').strip()
            mgr_phone = rec.get('managerphone', '').strip()
            mgr_email = rec.get('mangeremail', '').strip() or rec.get('manageremail', '').strip()

            username = rec.get('username', '').strip() or mgr_email or f"fac_{normalize_key(h_name)[:12]}_{idx}"
            password = rec.get('password', '').strip() or 'Facility@12345'

            try:
                user = None
                user_email = mgr_email or (username if '@' in username else f"{username}@meetadr.local")
                if user_email:
                    if not User.objects.filter(email=user_email).exists():
                        user = User.objects.create_user(
                            email=user_email,
                            password=password,
                            role=UserRole.HOSPITAL,
                            name=mgr_name or h_name,
                        )

                if is_clinic:
                    fac = Clinic.objects.create(
                        name=h_name,
                        country=country,
                        emirate=emirate,
                        location=emirate,
                        area=area,
                        address=address,
                        latitude=lat,
                        longitude=lng,
                        phone_dial_code=dial_code,
                        phone=main_phone,
                        website=website,
                        about=about,
                        photo=photo,
                        logo=logo,
                        insurance_plans=ins_raw,
                        facility_category='Clinic',
                        manager_name=mgr_name,
                        manager_phone=mgr_phone,
                        manager_email=mgr_email,
                        admin_user=user,
                        status=FacilityStatus.ACTIVE,
                    )
                else:
                    fac = Hospital.objects.create(
                        name=h_name,
                        country=country,
                        emirate=emirate,
                        location=emirate,
                        area=area,
                        address=address,
                        latitude=lat,
                        longitude=lng,
                        phone_dial_code=dial_code,
                        phone=main_phone,
                        website=website,
                        about=about,
                        photo=photo,
                        logo=logo,
                        insurance_plans=ins_raw,
                        facility_category=cat_norm,
                        manager_name=mgr_name,
                        manager_phone=mgr_phone,
                        manager_email=mgr_email,
                        admin_user=user,
                        status=FacilityStatus.ACTIVE,
                    )

                created_count += 1
                created_facilities.append({'id': str(fac.id), 'name': fac.name, 'type': 'clinic' if is_clinic else 'hospital'})
            except Exception as e:
                errors.append({'record': idx, 'name': h_name, 'error': str(e)})

        log_audit_event(
            action="BULK_IMPORT_HOSPITALS",
            target_model="Hospital",
            target_id="bulk",
            actor=request.user,
            change_summary={"total": len(records), "imported": created_count, "errors": len(errors)},
            request=request
        )

        return Response({
            'success': True,
            'total_records': len(records),
            'imported': created_count,
            'errors': errors,
            'facilities': created_facilities,
        }, status=status.HTTP_201_CREATED if created_count > 0 else status.HTTP_400_BAD_REQUEST)


class FacilityBulkImportDoctorsView(views.APIView):
    """
    Facility-scoped bulk doctor import for hospital/clinic administrators.
    POST /api/v1/facility/doctors/import/
    """
    permission_classes = [IsFacilityAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        fac_type, facility = get_facility_for_user(request.user)
        if not facility:
            raise PermissionDenied("User is not associated with an active healthcare facility.")

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            raise ValidationError({'file': 'Please upload an .xlsx or .csv file.'})

        fname = uploaded_file.name.lower()
        content = uploaded_file.read()

        try:
            if fname.endswith('.xlsx'):
                matrix = parse_xlsx_cells(content)
            elif fname.endswith('.csv'):
                matrix = parse_csv_cells(content)
            else:
                raise ValidationError({'file': 'Only .xlsx and .csv file formats are supported.'})
        except Exception as e:
            return Response({'error': f'Failed to parse file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        records = extract_records(matrix)
        if not records:
            return Response({'error': 'No data records found in file.'}, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        errors = []
        created_doctors = []

        is_hosp = fac_type == 'hospital'

        for idx, rec in enumerate(records, 1):
            first_name = rec.get('firstname', '').strip()
            last_name = rec.get('lastname', '').strip()
            if not first_name and not last_name:
                continue

            full_name = f"Dr. {first_name} {last_name}".strip()
            if not full_name or full_name == 'Dr.':
                full_name = rec.get('doctorfullname', '').strip() or 'Dr. Specialist'

            dept = rec.get('department', '').strip()
            gender = rec.get('gender', 'Male').strip().capitalize()
            if gender not in ['Male', 'Female', 'Other']:
                gender = 'Male'

            quals_raw = rec.get('qualifications', '').strip()
            qualifications = [q.strip() for q in quals_raw.split(',') if q.strip()]

            specialty = rec.get('speciality', '').strip() or rec.get('specialty', '').strip() or 'General Medicine'

            interests_raw = rec.get('specialintrests', '').strip() or rec.get('specialinterests', '').strip()
            special_interests = [s.strip() for s in interests_raw.split(',') if s.strip()]

            exp_raw = rec.get('yearsofexperience', '').strip()
            exp_num = 5
            if exp_raw:
                digits = re.findall(r'\d+', exp_raw)
                if digits:
                    try:
                        exp_num = int(digits[0])
                    except:
                        exp_num = 5

            country_origin = rec.get('countryoforigin', '').strip() or 'United Arab Emirates'
            langs_raw = rec.get('languagespoken', '').strip() or rec.get('languages', '').strip()
            languages = [l.strip() for l in langs_raw.split(',') if l.strip()] or ['English', 'Arabic']

            dial_code = rec.get('clinicdialcode', '').strip() or rec.get('countrycodearea971uae', '').strip() or '+971'
            if not dial_code.startswith('+') or len(dial_code) > 16:
                dial_code = '+971'
            contact_number = rec.get('contactnumber', '').strip()
            email = rec.get('email', '').strip()
            about = rec.get('doctorprofile', '').strip() or f"{full_name} is an experienced specialist at {facility.name}."
            photo = rec.get('doctorimagefilename', '').strip() or rec.get('photo', '').strip()

            username = rec.get('username', '').strip() or email or f"doc_{first_name.lower()}_{idx}"
            password = rec.get('password', '').strip() or 'Doctor@12345'

            try:
                user = None
                user_email = email or (username if '@' in username else f"{username}@meetadr.local")
                if user_email:
                    if not User.objects.filter(email=user_email).exists():
                        user = User.objects.create_user(
                            email=user_email,
                            password=password,
                            role=UserRole.DOCTOR,
                            name=full_name,
                        )

                doc = Doctor.objects.create(
                    user=user,
                    name=full_name,
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    department=dept,
                    qualifications=qualifications,
                    specialty=specialty,
                    special_interests=special_interests,
                    experience_years=exp_num,
                    country_of_origin=country_origin,
                    languages=languages,
                    phone_dial_code=dial_code,
                    contact_number=contact_number,
                    email=email,
                    about=about,
                    photo=photo,
                    hospital=facility if is_hosp else None,
                    clinic=facility if not is_hosp else None,
                    location=facility.location,
                    consultation_fee=Decimal('350.00'),
                    status=FacilityStatus.ACTIVE,
                )

                DoctorSchedule.objects.create(
                    doctor=doc,
                    available_days=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                    standard_slots=['09:00', '10:00', '11:00', '14:00', '15:00', '16:00'],
                )

                created_count += 1
                created_doctors.append({'id': str(doc.id), 'name': doc.name, 'specialty': doc.specialty})
            except Exception as e:
                errors.append({'record': idx, 'name': full_name, 'error': str(e)})

        return Response({
            'success': True,
            'total_records': len(records),
            'imported': created_count,
            'errors': errors,
            'doctors': created_doctors,
        }, status=status.HTTP_201_CREATED if created_count > 0 else status.HTTP_400_BAD_REQUEST)


class DownloadTemplateView(views.APIView):
    """
    Download official blank master Excel template for Doctors or Hospitals.
    GET /api/v1/admin/import/template/doctors/
    GET /api/v1/admin/import/template/hospitals/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, target):
        base_dir = settings.BASE_DIR.parent
        if target == 'doctors':
            file_path = os.path.join(base_dir, 'Template - Doctors Data.xlsx')
            fname = 'Template - Doctors Data.xlsx'
        elif target in ['hospitals', 'hospital']:
            file_path = os.path.join(base_dir, 'Template - HOSPTIAL Data.xlsx')
            fname = 'Template - HOSPTIAL Data.xlsx'
        else:
            raise ValidationError({'target': 'Invalid template target. Use "doctors" or "hospitals".'})

        if not os.path.exists(file_path):
            return Response({'error': 'Template file not found on server.'}, status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(open(file_path, 'rb'), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response
