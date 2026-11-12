"""
Supabase Storage Integration Service.
Handles uploading, listing, and managing photos in Supabase Object Storage.
"""
import os
import re
import json
import urllib.request
import urllib.error
import mimetypes
from django.conf import settings

def get_storage_config():
    """Retrieve Supabase Storage configuration from environment or settings."""
    url = os.getenv('SUPABASE_STORAGE_URL') or getattr(settings, 'SUPABASE_STORAGE_URL', 'https://kpdichfdhrkcdivqebow.supabase.co')
    key = os.getenv('SUPABASE_STORAGE_KEY') or getattr(settings, 'SUPABASE_STORAGE_KEY', '')
    bucket = os.getenv('SUPABASE_STORAGE_BUCKET') or getattr(settings, 'SUPABASE_STORAGE_BUCKET', 'photos')
    return url.rstrip('/'), key, bucket

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to be URL-safe while preserving extension."""
    parts = filename.rsplit('.', 1)
    base = parts[0]
    ext = ('.' + parts[1].lower()) if len(parts) > 1 else ''
    
    # Replace spaces and non-alphanumeric (except dashes and underscores)
    base_clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', base)
    base_clean = re.sub(r'_+', '_', base_clean).strip('_')
    if not base_clean:
        base_clean = 'photo'
    return f"{base_clean}{ext}"

def upload_photo(file_bytes: bytes, filename: str, category: str = 'doctors', content_type: str = None) -> dict:
    """
    Upload a photo file to Supabase Storage in the specified category folder.
    category: 'doctors' | 'hospitals' | 'logos'
    """
    project_url, secret_key, bucket = get_storage_config()
    if not secret_key:
        raise ValueError("Supabase storage key is not configured in backend environment.")

    clean_category = category.strip().lower()
    if clean_category not in ['doctors', 'hospitals', 'logos']:
        clean_category = 'doctors'

    clean_filename = sanitize_filename(filename)
    path = f"{clean_category}/{clean_filename}"

    if not content_type:
        content_type, _ = mimetypes.guess_type(clean_filename)
    if not content_type or not content_type.startswith('image/'):
        content_type = 'image/jpeg'

    upload_url = f"{project_url}/storage/v1/object/{bucket}/{path}"

    req = urllib.request.Request(
        upload_url,
        data=file_bytes,
        headers={
            'Authorization': f'Bearer {secret_key}',
            'apikey': secret_key,
            'x-upsert': 'true',
            'Content-Type': content_type
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        raise RuntimeError(f"Supabase storage upload failed ({e.code}): {err_msg}")
    except Exception as e:
        raise RuntimeError(f"Storage connection error: {str(e)}")

    public_url = f"{project_url}/storage/v1/object/public/{bucket}/{path}"

    return {
        'name': clean_filename,
        'path': path,
        'category': clean_category,
        'url': public_url,
        'size': len(file_bytes),
        'content_type': content_type
    }

def list_photos(category: str = 'doctors', limit: int = 100, offset: int = 0) -> list:
    """
    List photos in Supabase Storage for the specified category folder.
    """
    project_url, secret_key, bucket = get_storage_config()
    if not secret_key:
        return []

    clean_category = category.strip().lower()
    if clean_category not in ['doctors', 'hospitals', 'logos']:
        clean_category = 'doctors'

    list_url = f"{project_url}/storage/v1/object/list/{bucket}"
    payload = {
        'prefix': f"{clean_category}",
        'limit': limit,
        'offset': offset,
        'sortBy': {'column': 'created_at', 'order': 'desc'}
    }

    req = urllib.request.Request(
        list_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {secret_key}',
            'apikey': secret_key,
            'Content-Type': 'application/json'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return []

    results = []
    for item in data:
        # Ignore folder placeholders
        name = item.get('name')
        if not name or name.endswith('/'):
            continue

        path = f"{clean_category}/{name}"
        public_url = f"{project_url}/storage/v1/object/public/{bucket}/{path}"
        meta = item.get('metadata') or {}
        
        results.append({
            'name': name,
            'path': path,
            'category': clean_category,
            'url': public_url,
            'size': meta.get('size', 0),
            'content_type': meta.get('mimetype', 'image/jpeg'),
            'created_at': item.get('created_at'),
            'updated_at': item.get('updated_at')
        })

    return results

def delete_photo(path: str) -> bool:
    """
    Delete a photo by path (e.g. 'doctors/dr_ahmed.jpg').
    """
    project_url, secret_key, bucket = get_storage_config()
    if not secret_key:
        return False

    del_url = f"{project_url}/storage/v1/object/{bucket}"
    payload = {'prefixes': [path]}

    req = urllib.request.Request(
        del_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {secret_key}',
            'apikey': secret_key,
            'Content-Type': 'application/json'
        },
        method='DELETE'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False

