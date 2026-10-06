"""OpenAPI Schema Postprocessing Hooks for drf-spectacular."""

def categorize_swagger_tags(result, generator, request, public):
    """
    Groups all API endpoints into clear business domains for Swagger UI:
    Authentication, Bookings, Patient, Doctor, Hospital Admin, Admin,
    Prescriptions, Discovery & Facilities, Notifications & System.
    """
    paths = result.get('paths', {})
    for path, methods in paths.items():
        for method, op in methods.items():
            if not isinstance(op, dict) or 'tags' not in op:
                continue

            if '/auth/' in path:
                tag = 'Authentication'
            elif '/admin/' in path and not ('/hospital' in path or '/facility' in path):
                tag = 'Admin'
            elif '/hospital/' in path or '/facility/' in path or '/hospital-admin/' in path:
                tag = 'Hospital Admin'
            elif '/doctor/' in path or '/doctors/' in path:
                tag = 'Doctor'
            elif '/patient/' in path:
                tag = 'Patient'
            elif '/appointments/' in path or '/bookings/' in path:
                tag = 'Bookings'
            elif '/prescriptions/' in path:
                tag = 'Prescriptions'
            elif '/notifications/' in path or '/health/' in path:
                tag = 'Notifications & System'
            elif any(k in path for k in ['/hospitals/', '/clinics/', '/specialties/', '/conditions/', '/provider-requests/']):
                tag = 'Discovery & Facilities'
            else:
                tag = 'General'

            op['tags'] = [tag]

    return result
