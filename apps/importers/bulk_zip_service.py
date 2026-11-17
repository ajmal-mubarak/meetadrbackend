"""
Enterprise Bulk Doctor Importer with ZIP Headshots Support.
Handles safe ZIP validation, image matching, optimization (WebP/JPEG),
Supabase Storage upload, and asynchronous/staged doctor creation.
"""
import io
import os
import re
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Tuple
from django.db import transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.conf import settings
from PIL import Image, ImageOps

from apps.doctors.models import Doctor, BulkDoctorImportJob
from apps.facilities.models import Hospital, Clinic, FacilityStatus
from apps.accounts.models import UserRole
from apps.importers.storage_service import upload_photo

User = get_user_model()

ALLOWED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_UNCOMPRESSED_ZIP_SIZE = 600 * 1024 * 1024  # 600 MB safety limit


def normalize_key(val: str) -> str:
    """Normalize a string key for tolerant lookup."""
    if not val:
        return ''
    # remove punctuation and spaces, convert to lowercase
    return re.sub(r'[^a-zA-Z0-9]', '', str(val)).lower()


class BulkDoctorZipService:
    """Service to handle Excel + ZIP bulk doctor onboarding."""

    @staticmethod
    def inspect_zip(zip_file_obj) -> Tuple[Dict[str, str], List[str], int]:
        """
        Inspect zip archive safely without extracting all files to disk.
        Returns:
            - photo_map: { normalized_name: zip_internal_path }
            - invalid_files: list of unsupported or hidden file paths
            - total_uncompressed_size
        """
        photo_map = {}
        invalid_files = []
        total_size = 0

        # Handle file-like object or bytes
        z = zipfile.ZipFile(zip_file_obj)
        for info in z.infolist():
            # Skip directories
            if info.is_dir():
                continue

            filename = os.path.basename(info.filename)
            # Skip hidden files and macOS metadata
            if filename.startswith('.') or '__MACOSX' in info.filename:
                continue

            total_size += info.file_size
            if total_size > MAX_UNCOMPRESSED_ZIP_SIZE:
                raise ValueError(f"ZIP archive exceeds safe uncompressed limit of {MAX_UNCOMPRESSED_ZIP_SIZE // (1024*1024)} MB.")

            _, ext = os.path.splitext(filename)
            ext_lower = ext.lower()

            if ext_lower not in ALLOWED_IMAGE_EXTS:
                invalid_files.append(info.filename)
                continue

            base_name, _ = os.path.splitext(filename)
            norm_base = normalize_key(base_name)
            norm_full = normalize_key(filename)

            if norm_base:
                photo_map[norm_base] = info.filename
            if norm_full:
                photo_map[norm_full] = info.filename

        return photo_map, invalid_files, total_size

    @staticmethod
    def optimize_image(raw_bytes: bytes, max_dim: int = 800, quality: int = 85) -> Tuple[bytes, str]:
        """
        Process headshot image using Pillow:
        - Auto-orient EXIF
        - Convert RGBA/P to RGB
        - Resize with antialiasing
        - Output optimized WebP (or JPEG fallback)
        """
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            img = ImageOps.exif_transpose(img)

            if img.mode in ('RGBA', 'LA'):
                # Transparent backgrounds to white or preserve PNG/WebP
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Thumbnail maintaining aspect ratio
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

            out_buf = io.BytesIO()
            img.save(out_buf, format='WEBP', quality=quality, method=4)
            return out_buf.getvalue(), 'image/webp'
        except Exception:
            # If optimization fails, fallback to raw bytes
            return raw_bytes, 'image/jpeg'

    @classmethod
    def validate_and_preview(
        cls,
        excel_records: List[Dict[str, str]],
        zip_file_obj,
        target_hospital: Hospital = None,
        user=None
    ) -> BulkDoctorImportJob:
        """
        Performs non-destructive dry-run matching and returns a populated BulkDoctorImportJob.
        """
        z = zipfile.ZipFile(zip_file_obj)
        photo_map, invalid_files, _ = cls.inspect_zip(zip_file_obj)

        total_records = len(excel_records)
        matched_photos_count = 0
        missing_photos_count = 0
        duplicate_count = 0
        invalid_records_count = 0

        preview_doctors = []
        matched_zip_filenames = set()

        # Pre-fetch existing doctors for fast de-duplication
        existing_emails = set(
            Doctor.objects.exclude(email='').values_list('email', flat=True)
        )
        existing_user_emails = set(
            User.objects.values_list('email', flat=True)
        )
        existing_phones = set(
            Doctor.objects.exclude(contact_number='').values_list('contact_number', flat=True)
        )

        for idx, rec in enumerate(excel_records, start=1):
            doc_id = (
                rec.get('doctorid', '').strip()
                or rec.get('id', '').strip()
                or rec.get('license', '').strip()
                or rec.get('licensenumber', '').strip()
                or rec.get('empcode', '').strip()
                or rec.get('code', '').strip()
            )

            first_name = rec.get('firstname', '').strip()
            last_name = rec.get('lastname', '').strip()
            full_name = (
                rec.get('displaytitlefullnameenglish', '').strip()
                or rec.get('doctorname', '').strip()
                or rec.get('name', '').strip()
                or f"{first_name} {last_name}".strip()
            )
            specialty = rec.get('specialty', '').strip()
            dept = rec.get('department', '').strip() or specialty
            email = rec.get('doctoremail', '').strip() or rec.get('email', '').strip()
            contact_number = rec.get('contactnumber', '').strip() or rec.get('phone', '').strip()
            photo_field = (
                rec.get('doctorphotofilename', '').strip()
                or rec.get('doctorphotofilenameurl', '').strip()
                or rec.get('doctorphoto', '').strip()
                or rec.get('photofilename', '').strip()
                or rec.get('photoname', '').strip()
                or rec.get('image', '').strip()
                or rec.get('doctorphotourl', '').strip()
                or rec.get('photo', '').strip()
            )

            # Check validity
            row_errors = []
            if not full_name:
                row_errors.append("Doctor Name is required.")
            if not specialty:
                row_errors.append("Specialty is required.")

            is_valid = len(row_errors) == 0
            if not is_valid:
                invalid_records_count += 1

            # Check duplicate
            is_duplicate = False
            dup_reason = ""
            if email and (email.lower() in existing_emails or email.lower() in existing_user_emails):
                is_duplicate = True
                dup_reason = f"Email {email} already registered"
            elif contact_number and len(contact_number) >= 7 and contact_number in existing_phones:
                is_duplicate = True
                dup_reason = f"Phone {contact_number} already exists"

            if is_duplicate:
                duplicate_count += 1

            # Photo matching logic
            matched_zip_file = None

            # Try candidate lookup keys in priority:
            candidates = []
            if photo_field:
                candidates.append(normalize_key(photo_field))
                base_p, _ = os.path.splitext(photo_field)
                candidates.append(normalize_key(base_p))
            if doc_id:
                candidates.append(normalize_key(doc_id))
            if first_name and last_name:
                candidates.append(normalize_key(f"{first_name}_{last_name}"))
                candidates.append(normalize_key(f"{first_name}{last_name}"))
            if full_name:
                candidates.append(normalize_key(full_name))

            for cand in candidates:
                if cand and cand in photo_map:
                    matched_zip_file = photo_map[cand]
                    matched_zip_filenames.add(matched_zip_file)
                    break

            has_photo = bool(matched_zip_file)
            if has_photo:
                matched_photos_count += 1
            else:
                missing_photos_count += 1

            # Generate lightweight data URI preview for first 30 doctors
            thumbnail_b64 = None
            if matched_zip_file and len(preview_doctors) < 30:
                try:
                    raw_data = z.read(matched_zip_file)
                    thumb_bytes, mime = cls.optimize_image(raw_data, max_dim=96, quality=70)
                    import base64
                    thumbnail_b64 = f"data:{mime};base64,{base64.b64encode(thumb_bytes).decode('utf-8')}"
                except Exception:
                    thumbnail_b64 = None

            preview_doctors.append({
                'row': idx,
                'doctor_id': doc_id,
                'name': full_name,
                'department': dept,
                'specialty': specialty,
                'email': email,
                'contact_number': contact_number,
                'matched_photo': matched_zip_file,
                'thumbnail': thumbnail_b64,
                'has_photo': has_photo,
                'is_duplicate': is_duplicate,
                'dup_reason': dup_reason,
                'is_valid': is_valid,
                'errors': row_errors,
            })

        # Calculate unused photos in ZIP
        all_zip_valid_photos = set(photo_map.values())
        unused_photos = sorted(list(all_zip_valid_photos - matched_zip_filenames))

        job = BulkDoctorImportJob.objects.create(
            hospital=target_hospital if isinstance(target_hospital, Hospital) else None,
            created_by=user,
            status='preview_ready',
            total_records=total_records,
            processed_records=0,
            successful_records=0,
            failed_records=invalid_records_count,
            skipped_records=duplicate_count,
            matched_photos=matched_photos_count,
            missing_photos=missing_photos_count,
            unused_photos=len(unused_photos),
            preview_data={
                'doctors': preview_doctors,
                'unused_photos': unused_photos[:100],  # first 100 unused filenames
                'total_unused_count': len(unused_photos),
                'invalid_files_in_zip': invalid_files[:50],
                'hospital_name': getattr(target_hospital, 'name', 'Unassigned') if target_hospital else 'Unassigned',
                'facility_type': 'Clinic' if isinstance(target_hospital, Clinic) else ('Hospital' if target_hospital else 'Unassigned'),
            },
            error_log=[
                {'row': d['row'], 'name': d['name'], 'error': d['dup_reason'] or (', '.join(d['errors']))}
                for d in preview_doctors if d['is_duplicate'] or not d['is_valid']
            ]
        )
        return job

    @classmethod
    def execute_import(
        cls,
        job_id: str,
        excel_records: List[Dict[str, str]],
        zip_file_obj,
        target_hospital: Hospital = None,
        activate_immediately: bool = False
    ):
        """
        Executes the import in a background thread to prevent HTTP timeouts.
        """
        def _worker():
            try:
                job = BulkDoctorImportJob.objects.get(id=job_id)
                job.status = 'importing'
                job.preview_data = job.preview_data or {}
                job.preview_data['current_phase'] = 'Matching doctor headshots from ZIP...'
                job.preview_data['progress_percent'] = 5
                job.save(update_fields=['status', 'preview_data', 'updated_at'])

                z = zipfile.ZipFile(zip_file_obj)
                photo_map, _, _ = cls.inspect_zip(zip_file_obj)

                # 1. Pre-match, read bytes, and optimize on main thread safely
                items_to_upload = []
                for idx, rec in enumerate(excel_records, start=1):
                    photo_field = (
                        rec.get('doctorphotofilename', '').strip()
                        or rec.get('doctorphotofilenameurl', '').strip()
                        or rec.get('doctorphoto', '').strip()
                        or rec.get('photofilename', '').strip()
                        or rec.get('doctorphotourl', '').strip()
                        or rec.get('photo', '').strip()
                    )
                    doc_id = (
                        rec.get('doctorid', '').strip()
                        or rec.get('id', '').strip()
                        or rec.get('license', '').strip()
                        or rec.get('licensenumber', '').strip()
                        or rec.get('empcode', '').strip()
                    )
                    first_name = rec.get('firstname', '').strip()
                    last_name = rec.get('lastname', '').strip()
                    full_name = (
                        rec.get('displaytitlefullnameenglish', '').strip()
                        or rec.get('doctorname', '').strip()
                        or rec.get('name', '').strip()
                        or f"{first_name} {last_name}".strip()
                    )
                    candidates = []
                    if photo_field:
                        candidates.append(normalize_key(photo_field))
                        base_p, _ = os.path.splitext(photo_field)
                        candidates.append(normalize_key(base_p))
                    if doc_id:
                        candidates.append(normalize_key(doc_id))
                    if first_name and last_name:
                        candidates.append(normalize_key(f"{first_name}_{last_name}"))
                    if full_name:
                        candidates.append(normalize_key(full_name))

                    matched_zip_file = None
                    for cand in candidates:
                        if cand and cand in photo_map:
                            matched_zip_file = photo_map[cand]
                            break

                    if matched_zip_file:
                        clean_filename = f"doc_{(doc_id or full_name).lower()}_{idx}.webp"
                        clean_filename = re.sub(r'[^a-zA-Z0-9_\.]', '_', clean_filename)
                        try:
                            raw_bytes = z.read(matched_zip_file)
                            webp_bytes, mime = cls.optimize_image(raw_bytes, max_dim=800, quality=85)
                            items_to_upload.append((idx, webp_bytes, clean_filename))
                        except Exception:
                            pass

                total_photos = len(items_to_upload)
                uploaded_photo_urls = {}
                uploaded_count = 0

                def _upload_worker(item):
                    r_idx, r_webp_bytes, r_clean_fn = item
                    try:
                        res = upload_photo(r_webp_bytes, r_clean_fn, category='doctors', content_type='image/webp')
                        return r_idx, res.get('url', '')
                    except Exception:
                        return r_idx, ''

                if items_to_upload:
                    job.preview_data['current_phase'] = f"Uploading photo 1 of {total_photos} to cloud storage..."
                    job.preview_data['progress_percent'] = 10
                    job.save(update_fields=['preview_data', 'updated_at'])

                    with ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_item = {executor.submit(_upload_worker, item): item for item in items_to_upload}
                        for future in as_completed(future_to_item):
                            r_idx, r_url = future.result()
                            if r_url:
                                uploaded_photo_urls[r_idx] = r_url
                            uploaded_count += 1
                            pct = 10 + int((uploaded_count / max(1, total_photos)) * 45)  # 10% -> 55%
                            job.preview_data['current_phase'] = f"Uploaded photo {uploaded_count} of {total_photos} to cloud storage..."
                            job.preview_data['progress_percent'] = pct
                            job.save(update_fields=['preview_data', 'updated_at'])

                # Pre-compute default password hash once (saves 700x PBKDF2 CPU hashing time)
                default_hashed_pw = make_password('Doctor@12345')

                processed = 0
                successful = 0
                failed = 0
                skipped = 0

                total_to_process = len(excel_records)
                job.preview_data['current_phase'] = "Writing doctor profiles and generating accounts..."
                job.preview_data['progress_percent'] = 60
                job.save(update_fields=['preview_data', 'updated_at'])

                BATCH_SIZE = 5
                for batch_start in range(0, total_to_process, BATCH_SIZE):
                    batch_slice = excel_records[batch_start:batch_start + BATCH_SIZE]
                    with transaction.atomic():
                        for batch_offset, rec in enumerate(batch_slice):
                            idx = batch_start + batch_offset + 1
                            processed += 1

                            first_name = rec.get('firstname', '').strip()
                            last_name = rec.get('lastname', '').strip()
                            full_name = (
                                rec.get('displaytitlefullnameenglish', '').strip()
                                or rec.get('doctorname', '').strip()
                                or rec.get('name', '').strip()
                                or f"{first_name} {last_name}".strip()
                            )
                            name_ar = rec.get('doctornamearabic', '').strip() or full_name
                            doc_id = (
                                rec.get('doctorid', '').strip()
                                or rec.get('id', '').strip()
                                or rec.get('license', '').strip()
                                or rec.get('licensenumber', '').strip()
                                or rec.get('empcode', '').strip()
                            )
                            gender = rec.get('gender', '').strip() or 'Male'
                            dept = rec.get('department', '').strip() or 'General Medicine'
                            specialty = rec.get('specialty', '').strip() or dept
                            qualifications = [q.strip() for q in rec.get('qualificationsdegrees', '').split(',') if q.strip()]
                            special_interests = [s.strip() for s in rec.get('specialinterestsconditions', '').split(',') if s.strip()]
                            country_origin = rec.get('countryoforigin', '').strip() or 'United Arab Emirates'
                            langs = [l.strip() for l in rec.get('languagesspoken', '').split(',') if l.strip()] or ['English', 'Arabic']
                            phone_dial = rec.get('countrydialcode', '').strip() or '+971'
                            contact_number = rec.get('contactnumber', '').strip()
                            email = rec.get('doctoremail', '').strip() or rec.get('email', '').strip()
                            about = rec.get('doctorprofilebiography', '').strip() or f"{full_name} is an accredited medical specialist."
                            exp_years = 5
                            try:
                                exp_years = int(re.findall(r'\d+', rec.get('yearsofexperience', '5'))[0])
                            except Exception:
                                exp_years = 5

                            # Skip invalid
                            if not full_name or not specialty:
                                failed += 1
                                continue

                            # Deduplication check
                            dup_q = Doctor.objects.none()
                            if email:
                                dup_q = Doctor.objects.filter(Q(email__iexact=email) | Q(user__email__iexact=email))
                            if not dup_q.exists() and contact_number:
                                dup_q = Doctor.objects.filter(contact_number=contact_number)
                            if not dup_q.exists():
                                if isinstance(target_hospital, Hospital):
                                    dup_q = Doctor.objects.filter(name__iexact=full_name, hospital=target_hospital, specialty__iexact=specialty)
                                elif isinstance(target_hospital, Clinic):
                                    dup_q = Doctor.objects.filter(name__iexact=full_name, clinic=target_hospital, specialty__iexact=specialty)

                            if dup_q.exists():
                                skipped += 1
                                continue

                            photo_url = uploaded_photo_urls.get(idx, '')

                            # Create user account with pre-hashed default password
                            user_email = email or f"doc_{normalize_key(doc_id or full_name)}_{idx}@meetadr.local"
                            doc_user = None
                            try:
                                if not User.objects.filter(email=user_email).exists():
                                    raw_pw = rec.get('password', '').strip()
                                    hashed_pw = default_hashed_pw if (not raw_pw or raw_pw == 'Doctor@12345') else make_password(raw_pw)
                                    doc_user = User(
                                        email=user_email,
                                        password=hashed_pw,
                                        role=UserRole.DOCTOR,
                                        name=full_name
                                    )
                                    doc_user.save()
                                else:
                                    doc_user = User.objects.filter(email=user_email).first()
                            except Exception:
                                pass

                            # Doctor status
                            status = FacilityStatus.ACTIVE if activate_immediately else FacilityStatus.DEACTIVATED

                            hosp_inst = target_hospital if isinstance(target_hospital, Hospital) else None
                            clinic_inst = target_hospital if isinstance(target_hospital, Clinic) else None
                            loc_val = getattr(target_hospital, 'location', '') or 'Dubai'

                            Doctor.objects.create(
                                user=doc_user,
                                name=full_name,
                                name_ar=name_ar,
                                first_name=first_name,
                                last_name=last_name,
                                gender=gender,
                                department=dept,
                                qualifications=qualifications,
                                specialty=specialty,
                                special_interests=special_interests,
                                country_of_origin=country_origin,
                                languages=langs,
                                phone_dial_code=phone_dial,
                                contact_number=contact_number,
                                email=email or (user_email if '@' in user_email and not user_email.endswith('@meetadr.local') else ''),
                                photo=photo_url,
                                experience_years=exp_years,
                                hospital=hosp_inst,
                                clinic=clinic_inst,
                                location=loc_val,
                                about=about,
                                status=status
                            )
                            successful += 1

                    # Update progress after batch commit
                    pct = 60 + int((processed / max(1, total_to_process)) * 38)
                    job.processed_records = processed
                    job.successful_records = successful
                    job.failed_records = failed
                    job.skipped_records = skipped
                    job.preview_data['current_phase'] = f"Imported {processed} of {total_to_process} doctors..."
                    job.preview_data['progress_percent'] = pct
                    job.save(update_fields=['processed_records', 'successful_records', 'failed_records', 'skipped_records', 'preview_data', 'updated_at'])

                job.status = 'completed'
                job.processed_records = processed
                job.successful_records = successful
                job.failed_records = failed
                job.skipped_records = skipped
                job.preview_data['current_phase'] = "Import completed successfully!"
                job.preview_data['progress_percent'] = 100
                job.save(update_fields=['status', 'processed_records', 'successful_records', 'failed_records', 'skipped_records', 'preview_data', 'updated_at'])

            except Exception as e:
                try:
                    job = BulkDoctorImportJob.objects.get(id=job_id)
                    job.status = 'failed'
                    job.error_log.append({'system_error': str(e)})
                    job.save()
                except Exception:
                    pass

        # Launch worker in background thread
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
