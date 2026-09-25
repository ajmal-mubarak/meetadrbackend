# MeetAdr — Security Architecture & Threat Model Blueprint
**Document ID:** `MEETADR-PHASE1-SEC`  
**Phase:** Phase 1 — Backend Architecture, Database Design & Security Blueprint  
**Status:** Security Architecture Revised — Pending User Approval  
**Classification:** Internal Technical Architecture & Compliance Reference  

---

## 1. Threat Model & Asset Classification

### 1.1 Core Assets & Impact Analysis

| Asset Category | Specific Data Elements | Confidentiality Impact | Integrity Impact | Availability Impact |
|---|---|---|---|---|
| **Patient Identifiable Information (PII)** | Full name, national identity, email, mobile number, emergency contact, date of birth, family dependents | HIGH | HIGH | MEDIUM |
| **Protected Health Information (PHI)** | Blood group, clinical allergies, chronic diagnoses, digital prescriptions, consultation notes, insurance policy numbers | CRITICAL | CRITICAL | HIGH |
| **Provider Financial & Administrative Data** | Facility commercial agreements, doctor fees, provider onboarding applications, contact information | HIGH | HIGH | MEDIUM |
| **Authentication & Access Credentials** | Password hashes (PBKDF2/Argon2), JWT signing keys, refresh token cookies, invitation setup tokens | CRITICAL | CRITICAL | CRITICAL |
| **Platform Availability & Scheduling** | Real-time doctor calendar slots, booking concurrency locks, system audit logs | MEDIUM | CRITICAL | CRITICAL |

### 1.2 Threat Actor Profiles & Attack Vectors

```
┌──────────────────┐     ┌────────────────────────────────────────────────────────┐
│  Threat Actor    │     │ Primary Attack Vectors & Objectives                    │
├──────────────────┤     ├────────────────────────────────────────────────────────┤
│ Malicious Public │ ──► │ • Credential stuffing & brute-force against auth APIs  │
│ Visitor          │     │ • Denial of Service via unauthenticated endpoint abuse │
│                  │     │ • Fake provider onboarding spam & registration attacks │
├──────────────────┤     ├────────────────────────────────────────────────────────┤
│ Compromised      │ ──► │ • Insecure Direct Object Reference (IDOR) on other     │
│ Patient Account  │     │   patients' appointments, prescriptions, or profiles   │
│                  │     │ • Race condition exploits to monopolize doctor slots   │
├──────────────────┤     ├────────────────────────────────────────────────────────┤
│ Rogue Facility   │ ──► │ • Cross-tenant data exfiltration (Hospital A viewing   │
│ Administrator    │     │   competing Hospital B doctors, patients, or metrics)  │
│                  │     │ • Tampering with affiliated doctor rosters or reviews  │
├──────────────────┤     ├────────────────────────────────────────────────────────┤
│ Compromised      │ ──► │ • Unauthorized access to unrelated patient records     │
│ Doctor Account   │     │ • Issuing fraudulent prescriptions                     │
├──────────────────┤     ├────────────────────────────────────────────────────────┤
│ Network          │ ──► │ • Man-in-the-Middle (MitM) token interception          │
│ Eavesdropper     │     │ • Cross-Site Request Forgery (CSRF) on session cookies │
└──────────────────┘     └────────────────────────────────────────────────────────┘
```

---

## 2. Authentication Threats & Password Policy

### 2.1 Credential Stuffing & Brute Force
- **Threat:** Automated botnets testing leaked credential dictionaries against `/api/v1/auth/login/`.
- **Mitigation Strategy:**
  - DRF Throttling: Strict per-IP and per-email rate limiting (`AnonRateThrottle`: 5 requests/minute for login; `ScopedRateThrottle`: 10 attempts/10 minutes per username).
  - Account lockout consideration: After 5 consecutive failed attempts within 15 minutes, temporary authentication cooldown on target account for 15 minutes.
  - Password strength validation: Full Django password validator suite (documented in Section 2.2).

### 2.2 Enterprise Password Policy & Validators
To ensure robust account defense, password validation does not rely solely on length. The backend enforces Django's full validator suite with custom healthcare complexity rules:
1. **`UserAttributeSimilarityValidator`:** Rejects passwords that closely resemble or contain the user's email, name, or phone number.
2. **`MinimumLengthValidator`:** Enforces a minimum length of **10 characters** (standard for healthcare and administrative accounts).
3. **`CommonPasswordValidator`:** Rejects passwords matching NIST/Django dictionaries of the 20,000 most commonly used passwords.
4. **`NumericPasswordValidator`:** Rejects passwords consisting entirely of numeric characters.
5. **Character Complexity Validator:** Requires a mix of uppercase letters, lowercase letters, and digits/special characters.

### 2.3 Token Security Strategy (Access vs Refresh Tokens, Session Cap & Token-Family Protection)
- **Threat:** Malicious browser extensions, compromised third-party scripts, or XSS vulnerabilities stealing stored tokens from `localStorage`.
- **Mitigation Strategy:**
  - **No Long-Lived Tokens in LocalStorage:** Long-lived refresh tokens are strictly barred from `localStorage` and `sessionStorage`.
  - **HttpOnly Cookie for Refresh Tokens:** Refresh tokens reside in an `HttpOnly`, `Secure` cookie (`meetadr_refresh_token`) scoped to `path='/api/v1/auth/'`. JavaScript cannot read this cookie.
  - **Short-Lived Access Tokens:** Access tokens live for only **15 minutes** and are kept in-memory within React state/closure.
  - **Refresh Token Lifetime & Non-Sliding Cap (30-Day Absolute Session Maximum):**
    - Refresh tokens have an individual lifetime of **7 days**.
    - Refresh tokens rotate on every `/api/v1/auth/token/refresh/` call, but **cannot slide indefinitely**.
    - An immutable `session_start_iat` claim tracks the original login timestamp. If `now > session_start_iat + 30 days`, the session expires definitively, rejecting further refreshes and requiring re-authentication.
  - **Token-Family & Reuse Detection:**
    - `ROTATE_REFRESH_TOKENS = True` and `BLACKLIST_AFTER_ROTATION = True`.
    - Every refresh token is tracked as part of a cryptographic token family.
    - If a previously rotated or revoked token is reused (indicating an attacker intercepted a prior token), SimpleJWT raises a token reuse error and invalidates the entire token family immediately.
  - **Blacklist Revocation on Logout:** Calling `/api/v1/auth/logout/` records the refresh token `jti` in the database blacklist table (`token_blacklist`), instantly invalidating the session.

---

## 3. Insecure Direct Object References (IDOR) & Clinical Relationship Authorization

Client-supplied identifiers are considered hostile by default.

### 3.1 IDOR Vulnerability Matrix & Backend Defense

| Endpoint | Attack Scenario | Vulnerable Pattern | MeetAdr Defense Pattern |
|---|---|---|---|
| `GET /api/v1/patient/profile/` | Patient A requests Patient B's profile | Accepting `?userId=usr_2` or path `/profile/{id}/` | Scoped strictly to `request.user.patient_profile`. No user ID accepted in route or query parameters. |
| `GET /api/v1/patient/dependents/{id}/` | Patient A accesses Patient B's dependent | Fetching `PatientDependent.objects.get(id=id)` without checking parent account | Scoped strictly to `request.user.patient_profile.dependents.filter(id=id)`. Foreign dependent ID returns `404 Not Found`. |
| `GET /api/v1/doctor/patients/{id}/profile/` | Doctor browses arbitrary patient medical records | Granting access based solely on the user having the `doctor` role | **Resource-level authorization:** Verifies doctor is active, facility is active, and an active clinical encounter exists (`Appointment` with status `confirmed` or `completed`) for this specific patient. Otherwise returns `404 Not Found`. |
| `GET /api/v1/appointments/{id}/` | Patient A queries `id` of Patient B's appointment | Fetching `Appointment.objects.get(id=id)` without checking ownership | Queryset scoped: `Appointment.objects.filter(Q(booked_by=request.user) \| Q(patient_profile__user=request.user))`. Foreign ID returns `404 Not Found`. |
| `POST /api/v1/appointments/{id}/cancel/` | Patient A cancels Patient B's appointment | Relying on client ID in body | Verifies `appointment.booked_by == request.user`. Returns `404 Not Found` if non-owner. |
| `POST /api/hospital-admin/appointments/{id}/cancel/` | Hospital A admin cancels Hospital B's appointment | Relying on admin role without facility relationship | Verifies `appointment.doctor.hospital == admin_facility` or `appointment.doctor.clinic == admin_facility`. Competing facility returns `404 Not Found`. |
| `GET /api/v1/prescriptions/{id}/` | Patient A reads Patient B's prescription | Fetching by PK | Object permission: checks `obj.patient == request.user or obj.doctor.user == request.user`. Rejects with `404`. |
| `PATCH /api/v1/hospital/doctors/{id}/status/` | Hospital A deactivates Hospital B's doctor | Using `Doctor.objects.get(id=id)` | Scoped queryset: `Doctor.objects.filter(hospital=request.user.hospital_facility)`. Cross-hospital ID returns `404`. |

---

## 4. Privilege Escalation Prevention

### 4.1 Registration Protection
- **Threat:** An attacker sends `{"role": "admin", "is_staff": true}` or `{"role": "hospital"}` to `POST /api/v1/auth/register/`.
- **Mitigation:**
  - The `PatientRegistrationSerializer` does not expose `role`, `is_staff`, or `is_superuser` fields in `Meta.fields`.
  - The model creation explicitly forces `role = 'patient'`, `is_staff = False`, `is_superuser = False`.
  - Any unexpected or privileged fields are stripped before database insertion.

### 4.2 Administrative Role Separation
- **Administrative Privileges:** Controlled exclusively by server administrators via the server console or pre-existing superusers.
- **Provider Account Creation:** Hospital and Clinic administrator accounts can only be provisioned via the superadmin approval of a verified `ProviderRequest`.

---

## 5. Provider Isolation Blueprint (Multi-Tenancy)

Hospital A must have zero visibility into Hospital B's operations, appointments, doctors, and analytics.

```
                              ┌───────────────────────────────────────────────┐
                              │           Incoming HTTP Request               │
                              │           (Authorization: Bearer <token>)     │
                              └───────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │ Authentication Middleware    │
                                       │ Populates request.user       │
                                       └──────────────┬───────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │ Permission Class Validation  │
                                       │ IsFacilityAdmin:             │
                                       │ user.role == 'hospital'      │
                                       └──────────────┬───────────────┘
                                                      │
                                                      ▼
                       ┌─────────────────────────────────────────────────────────────┐
                       │ ViewSet Queryset Resolution (get_queryset)                  │
                       ├─────────────────────────────────────────────────────────────┤
                       │ if hasattr(user, 'hospital_facility'):                      │
                       │     return Doctor.objects.filter(                           │
                       │         hospital=user.hospital_facility                     │
                       │     )                                                       │
                       │ elif hasattr(user, 'clinic_facility'):                      │
                       │     return Doctor.objects.filter(                           │
                       │         clinic=user.clinic_facility                         │
                       │     )                                                       │
                       │ return Doctor.objects.none()                                │
                       └─────────────────────────────────────────────────────────────┘
```

### Key Principles:
1. **Never Trust Request Body / Parameters:**
   Ignoring `hospitalId` or `clinicId` in request bodies. The backend overrides any such keys with the server-side relationship of `request.user`.
2. **Fail-Safe Negative Default:**
   If a user possesses `role='hospital'` but has no affiliated facility record attached, `get_queryset()` returns `Doctor.objects.none()` rather than defaulting to an open query.
3. **Information Disclosure Prevention:**
   Cross-tenant access attempts return `404 Not Found` rather than `403 Forbidden` to prevent malicious actors from enumerating the existence of competitor records.

---

## 6. Cookie Architecture, CORS & CSRF Defense

Cookie configuration and CSRF defenses must be designed around the **actual deployment topology**, distinguishing cross-origin from cross-site behavior.

### 6.1 Deployment Architecture & SameSite Strategy

```
Scenario A: Same-Site Deployment (Recommended Production)
Frontend:  https://app.meetadr.com  (or https://meetadr.com)
Backend:   https://api.meetadr.com
Relationship: Cross-Origin (different subdomains), but SAME-SITE (shared registrable domain: meetadr.com)
Cookie Config: SameSite='Lax', Secure=True, HttpOnly=True
Behavior: Browsers allow credentials (withCredentials: true) on AJAX/fetch between subdomains of the same registrable domain.

Scenario B: Cross-Site Deployment (e.g. Cloud Staging / Multi-Provider Hosting)
Frontend:  https://meetadr.vercel.app
Backend:   https://meetadr-api.run.app (or onrender.com)
Relationship: CROSS-SITE (different effective top-level domains: vercel.app vs run.app)
Cookie Config: SameSite='None', Secure=True, HttpOnly=True
Behavior: Browsers strictly require SameSite='None' and Secure=True to attach cookies across distinct eTLD+1 domains.
```

#### Environment-Configurable Cookie Settings:
Rather than hardcoding `SameSite=Lax`, the backend configuration evaluates the deployment environment:
```python
# Deployment-aware cookie configuration
AUTH_COOKIE_NAME = "meetadr_refresh_token"
AUTH_COOKIE_PATH = "/api/v1/auth/"
AUTH_COOKIE_HTTPONLY = True
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "True").lower() == "true"
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")  # 'Lax' for Scenario A; 'None' for Scenario B
```

### 6.2 Cross-Origin Resource Sharing (CORS) Configuration
- **No Wildcard Allowed:** `CORS_ALLOW_ALL_ORIGINS = False`.
- **Explicit Allowed Origins:** Loaded strictly from environment variables:
  ```python
  CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
  CORS_ALLOW_CREDENTIALS = True
  ```
- **Allowed Headers:** Explicitly whitelisted (`Authorization`, `Content-Type`, `X-CSRFToken`).

### 6.3 Cross-Site Request Forgery (CSRF) Defense
1. **Bearer Tokens on General API:**
   All operational API endpoints (`/appointments/`, `/doctors/`, `/patient/`, etc.) authenticate via `Authorization: Bearer <access_token>`. Bearer authentication is immune to CSRF because browsers do not automatically attach custom `Authorization` headers.
2. **CSRF Protection on Cookie Endpoints:**
   Endpoints that accept the refresh cookie (`/api/v1/auth/token/refresh/` and `/api/v1/auth/logout/`) are vulnerable to CSRF, especially in Scenario B (`SameSite=None`).
   - **Protection Mechanism:** Enforce Django's CSRF token validation (`X-CSRFToken` header matching the `csrftoken` cookie).
   - In cross-site environments, the frontend must retrieve the CSRF token from the server and attach it in the `X-CSRFToken` request header for any cookie-bearing POST requests.

---

## 7. Sensitive & Medical Data Protection (PHI / PII)

Healthcare data is protected with enterprise defense-in-depth:

1. **Transport Layer Security (TLS/HTTPS):**
   All production communication is strictly encrypted over TLS 1.3 / HTTPS. HTTP requests are redirected via `SECURE_SSL_REDIRECT = True`.
2. **Access Minimization:**
   - Patient medical profiles (allergies, blood group, emergency contact) are accessible only to the patient and to the doctor during an active consultation.
   - Prescriptions are strictly isolated between the issuing doctor and the patient.
3. **Data Retention & Soft Deletion:**
   - Historical medical records (completed appointments and prescriptions) are protected with `on_delete=models.PROTECT`. They are never casually cascaded or purged if an account is closed.

---

## 8. Appointment Concurrency & Double-Booking Protection

### 8.1 The Authoritative Protection: PostgreSQL Unique Constraint
The authoritative, race-proof foundation preventing duplicate active bookings is the **PostgreSQL conditional unique index**:
```python
models.UniqueConstraint(
    fields=['doctor', 'date', 'time_slot'],
    condition=models.Q(status__in=['confirmed', 'pending']),
    name='unique_active_doctor_slot'
)
```
- **Why this is authoritative:** PostgreSQL guarantees uniqueness at the storage engine level during index commit. No matter how many concurrent requests bypass application-level checks, PostgreSQL will physically reject conflicting row inserts with an `IntegrityError`.
- **Application Conflict Translation:** The backend catches `IntegrityError` inside `transaction.atomic()` and translates it into a standard `409 Conflict` response with error code `SLOT_ALREADY_BOOKED`.

### 8.2 Evaluation of Locking Strategy vs Targeted Approach
- **Evaluation of `Doctor.select_for_update()`:**
  Acquiring a row lock on the parent `Doctor` entity locks the doctor record across *all* dates and times. If Patient 1 is booking Monday at 9:00 AM and Patient 2 is booking Friday at 3:00 PM, a global doctor lock unnecessarily blocks Patient 2 until Patient 1's transaction commits. This creates an artificial latency bottleneck and high lock contention.
- **Targeted Application Concurrency Strategy:**
  1. **Availability Validation:** Fast read check verifying doctor practicing days, standard slots, and doctor/facility active status.
  2. **Active Conflict Check:** Application-level `filter(doctor=doctor, date=date, time_slot=time_slot, status__in=['confirmed', 'pending']).exists()` to return early for typical UX.
  3. **Atomic Insert & Constraint Catch:** Execute insertion inside `transaction.atomic()`. Rely on the PostgreSQL unique index as the authoritative race-condition barrier.
  4. **Optional Slot-Level Locking:** If high-load environments require serialized slot checks before insert, locking must be targeted at the specific slot/date tuple (e.g. via a dedicated slot model or advisory lock on `hash(doctor_id, date, time_slot)`), avoiding global `Doctor` table locks.
  5. **Do Not Rely on Locks Alone:** Row locking alone does not prevent double-booking across distributed connections or isolation levels; the PostgreSQL unique constraint is the mandatory authoritative guarantee.

---

## 9. Throttling, Rate Limiting & Abuse Prevention

API endpoints are protected using Django REST Framework's tiered throttling engine:

| Endpoint Tier | Scope | Rate Limit (Anonymous) | Rate Limit (Authenticated) | Rationale |
|---|---|---|---|---|
| **Authentication** | `login`, `register`, `refresh` | 5 / min | 10 / min | Prevents brute-force credential stuffing |
| **Provider Applications** | `provider-requests` | 3 / hour | 5 / hour | Prevents partnership form spamming |
| **Appointment Booking** | `appointments` (create) | 0 (Auth required) | 10 / min | Prevents slot exhaustion attacks |
| **Reviews Submission** | `appointments/{id}/review/`| 0 (Auth required) | 5 / min | Prevents automated rating manipulation |
| **Public Directory Search** | `doctors`, `hospitals` | 60 / min | 120 / min | Protects database from scraping & denial of service |

---

## 10. Audit Logging & Data Minimization

Administrative actions and high-risk operational events are recorded in an immutable `AuditLog` table.

### 10.1 Strict Data Minimization Policy
To uphold healthcare confidentiality and privacy compliance, the `AuditLog` strictly forbids logging sensitive credentials or medical content.

**Explicitly Blacklisted Fields (NEVER STORED):**
- Passwords, password hashes, or credential reset tokens.
- Raw JWT access tokens, refresh tokens, or authorization headers.
- Invitation tokens, token hashes, or setup links.
- Clinical diagnoses, prescription details, consultation notes, or medical records.
- Unnecessary PII (e.g., patient national IDs, emergency contact numbers, home addresses).

### 10.2 Retention of Actor Email & IP Address
- **Security Purpose:**
  1. **Accountability & Non-repudiation:** Provides an undeniable record of which administrator approved/rejected a provider or modified doctor statuses.
  2. **Fraud & Intrusion Detection:** Correlates unexpected administrative actions with unfamiliar IP addresses or geographic anomalies.
- **Retention Strategy:**
  - **Primary Storage (Operational DB):** Retained for a rolling **90-day window**.
  - **Archival & Purging:** An automated quarterly task exports logs older than 90 days to encrypted, access-restricted cold storage with a mandatory **1-year compliance retention period**, after which records are permanently purged.

### 10.3 Permitted Audit Log Structure
```json
{
  "timestamp": "2026-09-25T21:15:00Z",
  "actor_id": "usr_admin_001",
  "actor_email": "admin@meetadr.demo",
  "actor_ip": "192.168.1.50",
  "action": "PROVIDER_REQUEST_APPROVED",
  "target_model": "ProviderRequest",
  "target_id": "req_88f2...",
  "change_summary": {
    "provider_type": "hospital",
    "facility_name": "City Care Specialty Hospital",
    "created_facility_id": "hosp_102a...",
    "invitation_token_issued": true
  }
}
```

---

## 11. Production Hardening Checklist

When deploying to a production PostgreSQL environment, the following Django security settings must be enforced:

```python
# Production Django Hardening
DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# HTTPS Protections
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS Configuration
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# NOTE ON PRELOAD: SECURE_HSTS_PRELOAD is False by default.
# Enabling HSTS preload is an irreversible deployment decision requiring confirmed,
# permanent HTTPS across the domain and all subdomains. Only enable after explicit verification.
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False").lower() == "true"

# Modern Security Headers (SECURE_BROWSER_XSS_FILTER removed - deprecated in modern browsers)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Readable by frontend client for X-CSRFToken header
SESSION_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")

# Hosts & CORS
ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")
CORS_ALLOWED_ORIGINS = os.environ["CORS_ALLOWED_ORIGINS"].split(",")
CORS_ALLOW_CREDENTIALS = True
```

---

## 12. Security Test Plan (Automated Security Testing)

A dedicated test suite `backend/tests/security/` will be implemented:

### Test Suite Specifications
1. **`test_idor_patient_appointment_isolation`:**
   - Patient A authenticates, attempts `GET /api/v1/appointments/{patient_b_appointment_id}/`.
   - **Expected Status:** `404 Not Found`.
2. **`test_idor_patient_cancel_protection`:**
   - Patient A authenticates, attempts `POST /api/v1/appointments/{patient_b_appointment_id}/cancel/`.
   - **Expected Status:** `404 Not Found`.
3. **`test_provider_hospital_isolation`:**
   - Hospital A authenticates, attempts `PATCH /api/v1/hospital/doctors/{hospital_b_doctor_id}/status/`.
   - **Expected Status:** `404 Not Found`.
4. **`test_privilege_escalation_registration`:**
   - Public client posts `{"email": "...", "role": "admin", "is_staff": true}` to `/api/v1/auth/register/`.
   - **Expected Status:** `201 Created` with `role == 'patient'` and `is_staff == False`.
5. **`test_slot_booking_concurrency_race`:**
   - Concurrently fire 10 threads trying to book the exact same slot.
   - **Expected Result:** **Exactly one active appointment exists for the same doctor/date/time slot.** Other concurrent requests receive an appropriate documented conflict (`409 Conflict`) or throttle (`429 Too Many Requests`) response.
6. **`test_prescription_doctor_patient_confidentiality`:**
   - Unrelated Doctor B or Patient C attempts `GET /api/v1/prescriptions/{id}/`.
   - **Expected Status:** `404 Not Found`.
7. **`test_refresh_token_rotation_and_blacklisting`:**
   - Exchange refresh token for new access token. Old refresh token immediately fails if reused.
   - Call logout; refresh token immediately blacklisted.
8. **`test_password_policy_enforcement`:**
   - Tests passwords failing similarity, length (<10), common dictionary, and character complexity rules.
