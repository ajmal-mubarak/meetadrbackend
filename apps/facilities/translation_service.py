"""
Automated Arabic Translation Service for Healthcare Facilities and Doctors.
Translates English metadata (names, about descriptions, addresses, hours) to Arabic
using a medical domain dictionary + live translation fallback with zero external dependencies.
"""
import urllib.request
import urllib.parse
import json
import logging
import re

logger = logging.getLogger(__name__)

UAE_LOCATIONS_MAP = {
    'dubai': 'دبي',
    'abu dhabi': 'أبوظبي',
    'sharjah': 'الشارقة',
    'ajman': 'عجمان',
    'ras al khaimah': 'رأس الخيمة',
    'fujairah': 'الفجيرة',
    'umm al quwain': 'أم القيوين',
    'al ain': 'العين',
    'jumeirah': 'جميرا',
    'deira': 'ديرة',
    'downtown': 'وسط المدينة',
    'healthcare city': 'مدينة دبي الطبية',
    'dubai healthcare city': 'مدينة دبي الطبية',
    'marina': 'المارينا',
    'dubai marina': 'دبي مارينا',
    'palm jumeirah': 'نخلة جميرا',
    'difc': 'مركز دبي المالي العالمي',
    'al jaddaf': 'الجداف',
    'al baraha': 'البراحة',
    'al wasl': 'الوصل',
    'al maryah island': 'جزيرة المارية',
}

COMMON_MEDICAL_TERMS = {
    'hospital': 'مستشفى',
    'clinic': 'عيادة',
    'medical center': 'مركز طبي',
    'health center': 'مركز صحي',
    'specialty hospital': 'مستشفى تخصصي',
    'general hospital': 'مستشفى عام',
    'royal hospital': 'مستشفى رويال',
    'day surgery center': 'مركز جراحة اليوم الواحد',
    'orthopedic': 'العظام',
    'cardiology': 'القلب',
    'sports medicine': 'الطب الرياضي',
    'dermatology': 'الجلدية والتجميل',
    'eye hospital': 'مستشفى العيون',
}

COMMON_HOURS_MAP = {
    'open 24/7': 'مفتوح على مدار الساعة 24/7',
    '24/7': 'على مدار الساعة 24/7',
    'mon - sun: 08:00 - 20:00': 'يومياً: 08:00 - 20:00',
    'mon - sat: 08:00 - 20:00': 'من الإثنين إلى السبت: 08:00 - 20:00',
    'sun - thu: 08:00 - 20:00': 'من الأحد إلى الخميس: 08:00 - 20:00',
    'daily: 8am-10pm': 'يومياً: 8 صباحاً - 10 مساءً',
    'daily: 08:00 - 22:00': 'يومياً: 08:00 - 22:00',
}

def translate_to_arabic(text: str) -> str:
    """
    Translates an English string to Arabic.
    1. Checks domain dictionary.
    2. Calls translation API with 3-second timeout.
    3. Falls back gracefully to original or rule-based string.
    """
    if not text or not str(text).strip():
        return ''
    
    cleaned = str(text).strip()
    lower = cleaned.lower()

    # Direct dictionary matches
    if lower in UAE_LOCATIONS_MAP:
        return UAE_LOCATIONS_MAP[lower]
    if lower in COMMON_HOURS_MAP:
        return COMMON_HOURS_MAP[lower]
    if lower in COMMON_MEDICAL_TERMS:
        return COMMON_MEDICAL_TERMS[lower]

    # Pattern: "{name} is an accredited medical hospital affiliated with MeetAdr."
    hosp_match = re.match(r'^(.+?)\s+is an accredited medical hospital affiliated with MeetAdr\.?$', cleaned, re.IGNORECASE)
    if hosp_match:
        fac_name = hosp_match.group(1).strip()
        fac_name_ar = translate_name_to_arabic(fac_name)
        return f"{fac_name_ar} صرح طبي معتمد شريك مع منصة MeetAdr يقدم رعاية صحية متعددة التخصصات."

    # Pattern: "{name} is an accredited specialized outpatient clinic affiliated with MeetAdr."
    clinic_match = re.match(r'^(.+?)\s+is an accredited specialized outpatient clinic affiliated with MeetAdr\.?$', cleaned, re.IGNORECASE)
    if clinic_match:
        fac_name = clinic_match.group(1).strip()
        fac_name_ar = translate_name_to_arabic(fac_name)
        return f"{fac_name_ar} عيادة طبية تخصصية معتمدة شريكة مع منصة MeetAdr للرعاية الصحية."

    # Live translation via Google Translate web API
    try:
        url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ar&dt=t&q=' + urllib.parse.quote(cleaned)
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                translated_parts = [part[0] for part in data[0] if part and len(part) > 0 and part[0]]
                if translated_parts:
                    return ''.join(translated_parts).strip()
    except Exception as exc:
        logger.warning(f"Translation API request failed for '{cleaned[:30]}': {exc}")

    # Fallback: if single or two words, ensure prefix
    return cleaned

def translate_name_to_arabic(name: str, facility_type: str = 'hospital') -> str:
    """Translates a facility name to Arabic with natural medical title prefix."""
    if not name or not name.strip():
        return ''
    translated = translate_to_arabic(name)
    prefix = 'مستشفى' if facility_type == 'hospital' else 'عيادة'
    if not any(w in translated for w in ['مستشفى', 'عيادة', 'مركز']):
        return f"{prefix} {translated}"
    return translated

def auto_translate_facility(facility):
    """
    Inspects facility fields and auto-populates missing Arabic fields.
    Called automatically on model save so zero manual translation is required.
    """
    facility_type = 'hospital' if hasattr(facility, 'emergency_available') else 'clinic'
    modified = False

    # 1. Name
    if not getattr(facility, 'name_ar', None) or not facility.name_ar.strip():
        if facility.name:
            facility.name_ar = translate_name_to_arabic(facility.name, facility_type)
            modified = True

    # 2. Location standardization
    if getattr(facility, 'location', None):
        loc_str = facility.location.strip()
        loc_lower = loc_str.lower()
        if loc_lower in UAE_LOCATIONS_MAP:
            # Capitalize standard English location
            proper_en = loc_str.title()
            if facility.location != proper_en:
                facility.location = proper_en
                modified = True

    # 3. Address
    if not getattr(facility, 'address_ar', None) or not facility.address_ar.strip():
        if getattr(facility, 'address', None):
            facility.address_ar = translate_to_arabic(facility.address)
            modified = True

    # 4. Operating Hours
    if not getattr(facility, 'operating_hours_ar', None) or not facility.operating_hours_ar.strip():
        if getattr(facility, 'operating_hours', None):
            facility.operating_hours_ar = translate_to_arabic(facility.operating_hours)
            modified = True

    # 5. About Description
    if not getattr(facility, 'about_ar', None) or not facility.about_ar.strip():
        if getattr(facility, 'about', None):
            facility.about_ar = translate_to_arabic(facility.about)
            modified = True

    return modified
