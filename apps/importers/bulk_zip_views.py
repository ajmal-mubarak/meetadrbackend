"""
API Views for Enterprise Bulk Doctor Import with ZIP Archive.
Provides Preview/Dry-run validation, background execution, and progress tracking.
"""
import io
import os
import re
import csv
import uuid
from django.conf import settings
try:
    import openpyxl
except ImportError:
    openpyxl = None
from rest_framework import views, status, permissions
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

from apps.accounts.permissions import IsPlatformAdmin, IsFacilityAdmin
from apps.facilities.models import Hospital, Clinic
from apps.doctors.models import BulkDoctorImportJob
from apps.importers.bulk_zip_service import BulkDoctorZipService


def resolve_target_facility(facility_id, user):
    """
    Resolves facility as either a Hospital or Clinic model instance.
    Returns user-friendly validation error if specified ID is not found.
    """
    if facility_id:
        # Check Hospital
        try:
            return Hospital.objects.get(id=facility_id)
        except (Hospital.DoesNotExist, ValueError):
            pass
        # Check Clinic
        try:
            return Clinic.objects.get(id=facility_id)
        except (Clinic.DoesNotExist, ValueError):
            pass
        raise ValidationError({
            'hospital_id': 'Selected healthcare facility was not found. Please choose an active hospital or clinic from the list.'
        })

    # Auto-assign if facility admin
    if hasattr(user, 'role'):
        if user.role == 'hospital':
            return getattr(user, 'hospital_profile', None)
        elif user.role == 'clinic':
            return getattr(user, 'clinic_profile', None)

    return None


def parse_spreadsheet_to_records(file_obj) -> list:
    """Parse uploaded XLSX or CSV file into list of normalized dicts."""
    name = getattr(file_obj, 'name', '').lower()
    records = []

    content = file_obj.read()
    file_obj.seek(0)

    if name.endswith('.csv'):
        # CSV parsing
        decoded = content.decode('utf-8-sig', errors='replace')
        reader = csv.DictReader(io.StringIO(decoded))
        for row in reader:
            normalized_row = {
                re.sub(r'[^a-zA-Z0-9]', '', str(k)).lower(): (str(v).strip() if v is not None else '')
                for k, v in row.items() if k
            }
            if any(normalized_row.values()):
                records.append(normalized_row)
    else:
        # Excel parsing
        global openpyxl
        if openpyxl is None:
            try:
                import openpyxl as ox
                openpyxl = ox
            except ImportError:
                raise ValidationError("Excel processing library (openpyxl) is not available on this server.")
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
        headers = []
        for cell in ws[1]:
            val = str(cell.value or '').strip()
            norm = re.sub(r'[^a-zA-Z0-9]', '', val).lower()
            headers.append(norm)

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            rec = {}
            for h, cell_val in zip(headers, row):
                if h:
                    rec[h] = str(cell_val).strip() if cell_val is not None else ''
            if any(rec.values()):
                records.append(rec)

    return records


class BulkDoctorZipPreviewView(views.APIView):
    """
    POST /api/v1/admin/import/doctors-zip/preview/
    Non-destructive validation of Excel + ZIP.
    Returns preview report detailing matched photos, missing photos, and unused photos.
    """
    permission_classes = [permissions.IsAuthenticated, (IsPlatformAdmin | IsFacilityAdmin)]

    def post(self, request):
        excel_file = request.FILES.get('file') or request.FILES.get('excel')
        zip_file = request.FILES.get('zip') or request.FILES.get('photos')

        if not excel_file:
            raise ValidationError({'file': 'Spreadsheet file (.xlsx or .csv) is required.'})
        if not zip_file:
            raise ValidationError({'zip': 'ZIP archive containing doctor photos is required.'})

        hospital_id = request.data.get('hospital_id') or request.data.get('facility_id')
        target_facility = resolve_target_facility(hospital_id, request.user)

        excel_records = parse_spreadsheet_to_records(excel_file)
        if not excel_records:
            raise ValidationError({'file': 'Spreadsheet is empty or headers could not be recognized.'})

        try:
            job = BulkDoctorZipService.validate_and_preview(
                excel_records=excel_records,
                zip_file_obj=zip_file,
                target_hospital=target_facility,
                user=request.user
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f"Failed to inspect archive: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'job_id': str(job.id),
            'status': job.status,
            'hospital_id': str(target_facility.id) if target_facility else None,
            'hospital_name': getattr(target_facility, 'name', 'Unassigned') if target_facility else 'Unassigned',
            'facility_type': 'Clinic' if isinstance(target_facility, Clinic) else ('Hospital' if target_facility else 'Unassigned'),
            'total_records': job.total_records,
            'matched_photos': job.matched_photos,
            'missing_photos': job.missing_photos,
            'unused_photos': job.unused_photos,
            'duplicate_records': job.skipped_records,
            'invalid_records': job.failed_records,
            'preview_data': job.preview_data,
            'error_log': job.error_log,
        }, status=status.HTTP_200_OK)


class BulkDoctorZipExecuteView(views.APIView):
    """
    POST /api/v1/admin/import/doctors-zip/execute/
    Executes the import with Excel + ZIP in background.
    """
    permission_classes = [permissions.IsAuthenticated, (IsPlatformAdmin | IsFacilityAdmin)]

    def post(self, request):
        excel_file = request.FILES.get('file') or request.FILES.get('excel')
        zip_file = request.FILES.get('zip') or request.FILES.get('photos')
        job_id = request.data.get('job_id')

        if not excel_file or not zip_file:
            raise ValidationError({'error': 'Both Excel file and ZIP archive are required.'})

        hospital_id = request.data.get('hospital_id') or request.data.get('facility_id')
        target_facility = resolve_target_facility(hospital_id, request.user)

        activate_immediately = str(request.data.get('activate_immediately', '')).lower() in ['true', '1', 'yes']

        excel_records = parse_spreadsheet_to_records(excel_file)

        # Reuse existing job or create a new execution job
        job = None
        if job_id:
            try:
                job = BulkDoctorImportJob.objects.get(id=job_id)
            except BulkDoctorImportJob.DoesNotExist:
                pass

        if not job:
            job = BulkDoctorImportJob.objects.create(
                hospital=target_facility if isinstance(target_facility, Hospital) else None,
                created_by=request.user,
                status='pending',
                total_records=len(excel_records)
            )

        # Cache file bytes for the background worker
        excel_copy = io.BytesIO(excel_file.read())
        zip_copy = io.BytesIO(zip_file.read())

        BulkDoctorZipService.execute_import(
            job_id=str(job.id),
            excel_records=excel_records,
            zip_file_obj=zip_copy,
            target_hospital=target_facility,
            activate_immediately=activate_immediately
        )

        return Response({
            'job_id': str(job.id),
            'status': 'importing',
            'message': f"Started import of {len(excel_records)} doctors in background.",
            'total_records': len(excel_records)
        }, status=status.HTTP_202_ACCEPTED)


class BulkDoctorZipStatusView(views.APIView):
    """
    GET /api/v1/admin/import/doctors-zip/status/<uuid:job_id>/
    Polls real-time progress of an import job.
    """
    permission_classes = [permissions.IsAuthenticated, (IsPlatformAdmin | IsFacilityAdmin)]

    def get(self, request, job_id):
        job = get_object_or_404(BulkDoctorImportJob, id=job_id)
        total = job.total_records or 1
        preview = job.preview_data or {}

        pct = preview.get('progress_percent')
        if pct is None:
            pct = min(100, int((job.processed_records / total) * 100)) if total > 0 else 0
        if job.status == 'completed':
            pct = 100

        current_phase = preview.get('current_phase')
        if not current_phase:
            if job.status == 'completed':
                current_phase = 'Import complete!'
            elif job.status == 'failed':
                current_phase = 'Import failed.'
            elif job.status == 'importing':
                current_phase = f"Processing {job.processed_records} of {total} records..."
            else:
                current_phase = 'Queued...'

        return Response({
            'job_id': str(job.id),
            'status': job.status,
            'percentage': pct,
            'current_phase': current_phase,
            'total_records': job.total_records,
            'processed_records': job.processed_records,
            'successful_records': job.successful_records,
            'failed_records': job.failed_records,
            'skipped_records': job.skipped_records,
            'matched_photos': job.matched_photos,
            'missing_photos': job.missing_photos,
            'unused_photos': job.unused_photos,
            'error_log': job.error_log,
            'updated_at': job.updated_at.isoformat(),
        })


class BulkDoctorZipTemplateDownloadView(views.APIView):
    """
    GET /api/v1/admin/import/doctors-zip/template/
    Download official Enterprise Excel template for Doctors + ZIP Photo matching.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        global openpyxl
        if openpyxl is None:
            try:
                import openpyxl as ox
                openpyxl = ox
            except ImportError:
                openpyxl = None

        if openpyxl is None:
            # Fallback to pre-generated template file on disk
            candidate_paths = [
                os.path.join(settings.BASE_DIR, 'Sample_Bulk_Doctors_Empty.xlsx'),
                os.path.join(settings.BASE_DIR.parent, 'Sample_Bulk_Doctors_Empty.xlsx') if hasattr(settings.BASE_DIR, 'parent') else None
            ]
            for p in candidate_paths:
                if p and os.path.exists(p):
                    with open(p, 'rb') as f:
                        data = f.read()
                    response = HttpResponse(
                        data,
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                    response['Content-Disposition'] = 'attachment; filename="Enterprise_Doctor_ZIP_Template.xlsx"'
                    return response
            return Response({'error': 'Template generator not available'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Doctors Bulk Import"

        headers = [
            "Doctor ID *",
            "Doctor Photo (Filename or URL)",
            "Hospital / Clinic Affiliation *",
            "Department *",
            "First Name *",
            "Last Name *",
            "Gender *",
            "Display Title / Full Name (English) *",
            "Doctor Name (Arabic)",
            "Specialty *",
            "Emirate / Location *",
            "Qualifications & Degrees",
            "Special Interests / Conditions",
            "Country of Origin",
            "Languages Spoken",
            "Country Dial Code",
            "Contact Number",
            "Doctor Email",
            "Years of Experience",
            "Doctor Profile / Biography",
            "Username / Email *",
            "Password"
        ]

        sample_row = [
            "D001",
            "D001.jpg",
            "Mediclinic Parkview Hospital",
            "Cardiology",
            "Ahmed",
            "Refaat",
            "Male",
            "Dr. Ahmed Refaat",
            "د. أحمد رفعت",
            "Interventional Cardiology",
            "Dubai",
            "MBBS, MD, FACC",
            "Heart Failure, Hypertension, Angioplasty",
            "United Arab Emirates",
            "English, Arabic, French",
            "+971",
            "0501112231",
            "ahmed.refaat@mediclinic.ae",
            "16",
            "Senior Consultant Cardiologist specializing in adult cardiovascular care and coronary interventions.",
            "ahmed.refaat@mediclinic.ae",
            "Doctor@123"
        ]

        # Header styling
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="0E7490", end_color="0E7490", fill_type="solid")
        alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws.append(headers)
        ws.append(sample_row)

        for col_idx, cell in enumerate(ws[1], start=1):
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = alignment
            ws.row_dimensions[1].height = 28
            # Auto-adjust column width
            col_letter = openpyxl.utils.get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = max(len(headers[col_idx-1]) + 4, 18)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = 'attachment; filename="Enterprise_Doctor_ZIP_Template.xlsx"'
        return response
