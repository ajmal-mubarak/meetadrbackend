# MeetAdr — Backend Architecture & Database Design Blueprint
**Document ID:** `MEETADR-PHASE1-ARCH`  
**Phase:** Phase 1 — Backend Architecture, Database Design & Security Blueprint  
**Status:** Architecture Blueprint Complete — Pending User Approval  
**Target Environment:** Django 5.x / Django REST Framework / PostgreSQL (Production) / SQLite (Dev)

---

## 1. System Overview

MeetAdr is a comprehensive healthcare appointment and provider discovery platform designed to connect patients with accredited doctors, hospitals, and specialized clinics across the UAE. The platform provides:
- **Public Healthcare Discovery:** Faceted search, multilingual (English/Arabic) doctor rosters, hospital departments, clinic specialties, and health condition directories.
- **Transactional Appointment Booking:** Real-time doctor schedule availability, concurrency-safe slot reservations, booking lifecycles (confirmed, completed, cancelled), and verified post-consultation reviews.
- **Role-Based Portals:** Dedicated operational interfaces for Patients, Doctors, Healthcare Providers (Hospitals and Clinics), and Platform Superadministrators.
- **Provider Partnership Onboarding:** Structured public onboarding application and administrative approval pipeline with secure, credential-less facility administrator provisioning.
- **Clinical Prescriptions Domain:** Structured medication and diagnosis records linked to completed consultations with strict patient-doctor confidentiality boundaries.

The backend is built as a stateless RESTful API serving a decoupled Single Page Application (React / TypeScript).

---

## 2. Existing Backend Status & Audit Review

An inspection of the workspace was conducted prior to blueprint creation:
- **Repository Layout:** Root workspace containing `frontend/` (completed UI & mock service layer) and `backend/`.
- **Existing Backend Components:**
  - `backend/README.md`: Initial placeholder documenting planned backend directory.
  - `backend/docs/frontend-backend-analysis.md` (`MEETADR-PHASE0-AUDIT`): Comprehensive Phase 0 audit detailing all 49 frontend routes, 4 application roles, mock entities, API contracts, and security vulnerabilities.
  - No pre-existing Django models, migrations, apps, or configuration were present in `backend/`.
- **Findings & Preservation:**
  - Because no Django project code had been generated yet, there is no legacy schema, existing database, or conflicting migration history to preserve or destroy.
  - The custom User model can be established cleanly at the very start of Phase 2, avoiding Django's complex custom user model migration pitfalls on populated databases.
  - All architecture definitions strictly adhere to the audited requirements in `frontend-backend-analysis.md` and the user's explicit architectural decisions.

---

## 3. Frontend-Derived Requirements & Contracts

The completed frontend (`frontend/src`) dictates the functional and data contracts for the backend:

1. **Authentication & Identity:**
   - Unified login entry point (`/login` and `/:role/login`) supporting `patient`, `doctor`, `hospital`, and `admin`.
   - Patient self-registration.
   - Session persistence without storing raw long-lived tokens in insecure client storage.
   - User profile endpoints (`/api/v1/auth/me/`) returning role, contact details, and facility/doctor association keys.

2. **Healthcare Directory Services:**
   - Multi-parameter doctor filtering: specialty, location/emirate, hospital/clinic affiliation, practicing days, rating, search keyword.
   - Hospital profiles: accredited facilities, bed capacities, clinical departments, affiliated doctors roster, emergency status (24/7 ER availability), bilingual details (`nameAr`, `addressAr`, `operatingHoursAr`, `aboutAr`).
   - Clinic profiles: specialized outpatient clinics, primary specialty focus, affiliated doctors roster, bilingual details.
   - Medical conditions directory: A-Z index linking clinical conditions and symptoms to recommended medical specialties.

3. **Booking & Concurrency Engine:**
   - Dynamic availability calculator returning available practicing days and standard 30-minute consultation slots for any given date.
   - Concurrency-safe appointment creation eliminating double-booking under race conditions.
   - Appointment lifecycle state machine: `pending` → `confirmed` → `completed` or `cancelled`.
   - Comprehensive cancellation tracking: recording reason, cancel notes, cancelling actor role (`patient`, `doctor`, `hospital`, `admin`), and cancelling user ID.

4. **Clinical Records & Prescriptions:**
   - Structured digital prescription generation upon consultation completion.
   - Relational medication modeling: medication name, dosage, frequency, duration, and instructions.
   - Strict medical privacy: accessible exclusively to the attending doctor and the owning patient.

5. **Patient Health Profile & Family Care:**
   - Medical health metrics: blood group, allergies, chronic conditions, emergency contact, insurance provider and policy number.
   - Dependents management: adding and removing family members (spouse, child, parent, sibling) under the primary patient account.

6. **Provider Onboarding & Management:**
   - 3-step public application wizard (`/join`, `/become-a-partner`).
   - Admin review console (`/admin/requests`): approval and rejection workflows.
   - Automated creation of deactivated facility, secure invitation token delivery, and self-service password establishment.
   - Provider portal: managing affiliated doctors (adding to roster, toggling active/inactive status), departments, and facility operational settings.

---

## 4. User Roles & Permission Boundaries

The platform strictly defines **four application roles**:

```
                  ┌────────────────────────────────────────────────┐
                  │                 MeetAdr Roles                  │
                  └──────────────────────┬─────────────────────────┘
                                         │
        ┌───────────────────┬───────────┴───────────┬───────────────────┐
        ▼                   ▼                       ▼                   ▼
    [ patient ]         [ doctor ]             [ hospital ]         [ admin ]
   - Self profile      - Own profile          - Own facility       - Platform oversight
   - Search & book     - Own schedule         - Own doctors only   - Verify providers
   - Cancel own appt   - Own consultations    - Own departments    - Activate/deactivate
   - Submit reviews    - Own patient records  - Own analytics      - System analytics
   - Manage dependents - Issue prescriptions  - Facility settings  - Audit logs
```

### Role Matrix & Authorization Scopes

| Role | Server-Side Identity | Access Scope & Object Boundaries | Restrictions & Prohibitions |
|---|---|---|---|
| **patient** | `User.role == 'patient'` linked to `PatientProfile` | • Read public healthcare directories<br>• Book appointments for self/dependents<br>• View/cancel own appointments<br>• Read own prescriptions<br>• Submit reviews for own completed visits<br>• Manage own profile & dependents | • Cannot access administrative APIs<br>• Cannot modify provider or doctor data<br>• Cannot inspect or cancel other patients' bookings<br>• Cannot access prescriptions of other patients |
| **doctor** | `User.role == 'doctor'` linked to `Doctor` via 1:1 | • View and edit own practicing days and slots<br>• View own scheduled consultations<br>• Update status of own appointments (`completed`, `cancelled`)<br>• View medical history of patients with active bookings<br>• Create and view prescriptions for own consultations | • Cannot view or modify schedules of other doctors<br>• Cannot view private appointments of other doctors<br>• Cannot modify facility-wide administrative settings<br>• Cannot create appointments on behalf of arbitrary patients |
| **hospital** | `User.role == 'hospital'` linked to `Hospital` OR `Clinic` | • View and update operational settings of own facility<br>• Add and manage doctors belonging to own facility<br>• Toggle activation status of doctors on own roster<br>• Manage departments of own hospital<br>• View aggregate analytics of own facility | • Strictly isolated to own facility (cannot view Hospital B)<br>• Cannot access platform superadmin APIs<br>• Cannot access private clinical consultation notes outside own facility scope<br>• Cannot alter platform-wide directories |
| **admin** | `User.role == 'admin'`, `is_staff=True`, `is_superuser=True` | • Platform-wide oversight and analytics<br>• Review, approve, or reject provider partnership requests<br>• Platform-wide activation/deactivation of doctors and facilities<br>• Inspect all platform appointments and execute administrative cancellations<br>• View audit logs and system analytics | • Administrative actions are strictly audited in `AuditLog`<br>• Cannot register directly through public registration APIs<br>• Requires server-controlled provisioning |

---

## 5. Authentication Architecture

### 5.1 Protocol & Token Strategy

Authentication is implemented using **JSON Web Tokens (JWT)** via `djangorestframework-simplejwt`, configured with a dual-token split architecture:

```
[ Frontend Client ] 
    │
    ├── 1. POST /api/v1/auth/login/ (email, password)
    │      ◄── Returns: 200 OK + Body: { access, user } 
    │                    + Set-Cookie: meetadr_refresh_token (HttpOnly, Secure, SameSite)
    │
    ├── 2. GET /api/v1/... (Authenticated Request)
    │      ─── Header: Authorization: Bearer <access_token>
    │      ◄── Returns: API Resource Data
    │
    ├── 3. POST /api/v1/auth/token/refresh/ (Access Token Expired)
    │      ─── Cookie automatically sent: meetadr_refresh_token
    │      ─── Header: X-CSRFToken: <csrf_token>
    │      ◄── Returns: 200 OK + Body: { access }
    │                    + Set-Cookie: new meetadr_refresh_token (Rotated)
    │
    └── 4. POST /api/v1/auth/logout/
           ─── Cookie sent: meetadr_refresh_token
           ─── Server: Blacklists refresh token in token_blacklist table
           ◄── Clears meetadr_refresh_token cookie
```

### 5.2 Token Specifications & Security Configuration

1. **Access Token:**
   - **Type:** Stateless JWT (HMAC-SHA256 or RS256).
   - **Lifetime:** Short-lived — **15 minutes**.
   - **Delivery:** Returned directly in JSON response payload.
   - **Client Storage:** Maintained strictly in-memory (React state / closure). Never written to `localStorage` or `sessionStorage` to mitigate persistent Cross-Site Scripting (XSS) extraction risks.
   - **Payload Claims:**
     ```json
     {
       "token_type": "access",
       "exp": 1727280900,
       "iat": 1727280000,
       "jti": "d3a2b4c1-...",
       "user_id": "usr_9b1deb4d-...",
       "email": "doctor@meetadr.demo",
       "role": "doctor",
       "doctor_id": "doc_4a1f...",
       "facility_id": "hosp_8e2a..."
     }
     ```

2. **Refresh Token, Session Lifecycle & Token-Family Protection:**
   - **Type:** Opaque JWT managed by SimpleJWT with database-backed blacklisting (`rest_framework_simplejwt.token_blacklist`).
   - **Token Lifetime:** **7 days**.
   - **Absolute Maximum Session Lifetime (30 Days — No Indefinite Sliding):**
     - Refresh tokens rotate upon each use, but **cannot slide indefinitely**.
     - An initial login claim (`session_start_iat` or `session_exp`) tracks the original authenticated session inception.
     - When refreshing tokens via `/api/v1/auth/token/refresh/`, if `now > session_start_iat + 30 days`, token rotation is halted and the refresh request is rejected with `SESSION_EXPIRED` (401), requiring explicit re-authentication.
   - **Token-Family & Reuse Detection:**
     - `ROTATE_REFRESH_TOKENS = True` and `BLACKLIST_AFTER_ROTATION = True`.
     - When a refresh token is used, it is immediately invalidated and replaced by a child token in the same session family.
     - If a previously rotated or revoked refresh token is presented again (indicating token compromise or replay), SimpleJWT's token blacklist raises an invalid token error, and the entire token family for that session is revoked immediately.
   - **Delivery & Scoping:**
     - Stored exclusively in an `HttpOnly` cookie named `meetadr_refresh_token` scoped to `Path = '/api/v1/auth/'`.
   - **Deployment-Aware Cookie Configuration:**
     - **Same-Site Topology (e.g. `app.meetadr.com` + `api.meetadr.com`):** Configured as `SameSite='Lax'`, `Secure=True`, `HttpOnly=True`. Requests between subdomains of the same registrable domain share same-site cookie scope.
     - **Cross-Site Topology (e.g. `meetadr.vercel.app` + `meetadr-api.run.app`):** Configured as `SameSite='None'`, `Secure=True`, `HttpOnly=True`. Required for modern browsers to send cookies across distinct eTLD+1 domains.
     - Settings are deployment-configurable via `AUTH_COOKIE_SAMESITE` (`'Lax'` or `'None'`) and `AUTH_COOKIE_SECURE` (`True` in production).
   - **CORS & CSRF Defense:**
     - `CORS_ALLOW_ALL_ORIGINS = False`. Origins are strictly loaded from `CORS_ALLOWED_ORIGINS`.
     - `CORS_ALLOW_CREDENTIALS = True`.
     - Endpoints processing the refresh cookie (`/token/refresh/`, `/logout/`) enforce Django CSRF protection (`csrftoken` + `X-CSRFToken` request header).
   - **Blacklisting on Logout:** Calling `POST /api/v1/auth/logout/` extracts the refresh token from the cookie, records its `jti` in `OutstandingToken` / `BlacklistedToken`, and clears the cookie.

### 5.3 Password Management & Enterprise Credentials Policy

- **Hashing Algorithm:** Django `PBKDF2PasswordHasher` with 720,000 iterations (default) or `Argon2PasswordHasher` (`argon2-cffi`).
- **Comprehensive Password Validators Suite:**
  - `UserAttributeSimilarityValidator`: Rejects passwords containing or closely resembling the user's email, name, or phone.
  - `MinimumLengthValidator`: Minimum **10 characters** (elevated standard for healthcare platform accounts).
  - `CommonPasswordValidator`: Checks against NIST/Django dictionary of 20,000 commonly compromised passwords.
  - `NumericPasswordValidator`: Prevents passwords composed entirely of digits.
  - `ComplexityValidator`: Enforces at least one uppercase letter, one lowercase letter, and at least one digit or special character.
- **Plaintext Prohibition:** Passwords are never logged, never cached in memory, and never transmitted in plain text across backend services.

---

## 6. Authorization Architecture & Multi-Tenancy Isolation

Authorization in MeetAdr is enforced at the **view/queryset level** and the **object permission level**, derived strictly from `request.user`. The backend rejects and ignores any client-supplied tenant IDs (`hospitalId`, `clinicId`, `patientId`, `doctorId`).

### 6.1 Provider Isolation Engine (Hospitals & Clinics)

Hospital A must never view, modify, or leak data belonging to Hospital B or Clinic C.

```
                              [ Incoming Request ]
                                       │
                      Extract Authenticated User (request.user)
                                       │
                     Is user.role in ['hospital'] ?
                                ├── NO ──► 403 Forbidden
                                │
                               Yes
                                │
               Resolve Facility Relationship on Server:
               ┌───────────────────────┴───────────────────────┐
               ▼                                               ▼
     hasattr(user, 'hospital')                      hasattr(user, 'clinic')
               │                                               │
      facility = user.hospital                       facility = user.clinic
               │                                               │
      Queryset Scoped to:                            Queryset Scoped to:
      Doctor.objects.filter(                         Doctor.objects.filter(
        hospital=facility                              clinic=facility
      )                                              )
```

#### Server-Side Isolation Rules:
1. **Facility Context Resolution:**
   The backend inspects the authenticated user's related facility:
   ```python
   def get_user_facility(user):
       if hasattr(user, 'hospital_facility'):
           return ('hospital', user.hospital_facility)
       if hasattr(user, 'clinic_facility'):
           return ('clinic', user.clinic_facility)
       return (None, None)
   ```
2. **Queryset Scoping:**
   All provider-specific endpoints override `get_queryset()`:
   ```python
   class FacilityDoctorViewSet(viewsets.ModelViewSet):
       permission_classes = [IsAuthenticated, IsFacilityAdmin]
       
       def get_queryset(self):
           facility_type, facility = get_user_facility(self.request.user)
           if facility_type == 'hospital':
               return Doctor.objects.filter(hospital=facility)
           elif facility_type == 'clinic':
               return Doctor.objects.filter(clinic=facility)
           return Doctor.objects.none()

       def perform_create(self, serializer):
           facility_type, facility = get_user_facility(self.request.user)
           if facility_type == 'hospital':
               serializer.save(hospital=facility, clinic=None)
           elif facility_type == 'clinic':
               serializer.save(clinic=facility, hospital=None)
   ```
3. **Write Protection:**
   Even if the client sends `{ "hospitalId": "hosp_competing_99" }`, the serializer ignores incoming facility foreign keys and injects the authenticated `request.user`'s facility during `perform_create` / `perform_update`.
4. **Negative Authorization (IDOR Prevention):**
   Attempting `PATCH /api/v1/hospital/doctors/doc_competing_12/` results in `404 Not Found` (preferred to avoid leaking existence) because the doctor is outside the scoped queryset.

### 6.2 Patient Data Isolation Engine

1. **Appointment Creation:**
   `POST /api/v1/appointments/`:
   - `patient` is unconditionally set to `request.user`. Any incoming `patientId` or `patient_id` in the JSON body is rejected or discarded.
   - Guest booking is prohibited. Unauthenticated requests receive `401 Unauthorized`.
2. **Appointment Inspection & Cancellation:**
   - Patient appointment lists (`/api/v1/appointments/my/`) query `Appointment.objects.filter(patient=request.user)`.
   - Cancellation (`POST /api/v1/appointments/{id}/cancel/`):
     - Verified: `appointment.patient == request.user`.
     - Non-owning patients receive `404 Not Found`.
3. **Medical Profile & Dependents:**
   - `/api/v1/patient/profile/` resolves `PatientProfile.objects.get(user=request.user)`.
   - `/api/v1/patient/dependents/` resolves `request.user.patient_profile.dependents.all()`.
   - Dependents cannot be created, modified, or deleted without verifying that the parent profile matches `request.user.patient_profile`.

### 6.3 Doctor Data Isolation & Clinical Relationship Authorization

1. **Schedule Management:**
   - `PUT /api/v1/doctor/schedule/` resolves `request.user.doctor_profile.schedule`.
   - A doctor cannot update practicing days or time slots for any other doctor.
2. **Consultation & Appointment Access:**
   - Doctor dashboard queries `Appointment.objects.filter(doctor=request.user.doctor_profile)`.
   - Actions (`complete`, `cancel`): Object permission verifies `appointment.doctor.user == request.user`.
3. **Strict Doctor Access to Patient Medical Profile (Clinical Relationship Mandate):**
   - Access to a patient's medical profile is **NEVER granted merely because a user has the `doctor` role**, works at the same hospital/clinic, or possesses the patient's ID.
   - Resource-level authorization strictly verifies the following 6 conditions before granting access:
     1. The requesting user is authenticated.
     2. The user has the `doctor` role (`request.user.role == 'doctor'`).
     3. The doctor is associated with the relevant facility (`doctor.hospital` or `doctor.clinic` is `Active`).
     4. The doctor has a valid, active clinical relationship with that specific patient through an authorized appointment/encounter record.
     5. The requested patient (whether a primary patient or dependent patient) is the actual patient associated with that clinical relationship.
     6. The appointment/encounter is in an active/valid clinical state where access is permitted (`confirmed` or `completed`; never `cancelled`).
   - If no valid clinical relationship exists in an approved state, the backend rejects the request (`403 Forbidden` / `404 Not Found`). Arbitrary browsing of global patient records is blocked.

### 6.4 Superadmin Platform Security

1. **Server-Controlled Privileges:**
   - Admin access requires `user.role == 'admin'`, `user.is_staff == True`, and `user.is_superuser == True`.
   - The public registration endpoint (`/api/v1/auth/register/`) hardcodes `role='patient'` and explicitly prevents mass-assignment of `role`, `is_staff`, or `is_superuser`.
2. **Administrative Audit Trail:**
   - Every administrative status change (approving provider request, toggling doctor status, administrative cancellation) logs an immutable entry to `AuditLog`.

---

## 7. Database Entity Relationship Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     DATABASE ER DIAGRAM                                     │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────┐                     ┌───────────────────────────┐
    │     ProviderRequest  │                     │         AuditLog          │
    ├──────────────────────┤                     ├───────────────────────────┤
    │ id (UUID, PK)        │                     │ id (BigAutoField, PK)     │
    │ provider_type        │                     │ actor (FK -> User)        │
    │ name, name_ar        │                     │ action                    │
    │ contact_person       │                     │ target_model, target_id   │
    │ contact_email, phone │                     │ change_summary (JSON)     │
    │ status, notes        │                     │ ip_address, created_at    │
    └──────────────────────┘                     └───────────────────────────┘
               │ (Approved)
               ▼
    ┌──────────────────────┐                     ┌───────────────────────────┐
    │      Hospital        │                     │          Clinic           │
    ├──────────────────────┤                     ├───────────────────────────┤
    │ id (UUID, PK)        │                     │ id (UUID, PK)             │
    │ admin_user (1:1 User)│                     │ admin_user (1:1 User)     │
    │ name, name_ar        │                     │ name, name_ar             │
    │ location, address    │                     │ location, address         │
    │ phone, operating_hrs │                     │ phone, operating_hrs      │
    │ emergency_available  │                     │ primary_specialty         │
    │ status (Active/Deact)│                     │ status (Active/Deact)     │
    └──────────┬───────────┘                     └─────────────┬─────────────┘
               │ 1:N (FacilityDepartment)                      │
               ▼                                               │
    ┌──────────────────────┐                                   │
    │  FacilityDepartment  │                                   │
    ├──────────────────────┤                                   │
    │ id (UUID, PK)        │                                   │
    │ hospital (FK)        │                                   │
    │ name, head_of_dept   │                                   │
    │ bed_capacity         │                                   │
    └──────────────────────┘                                   │
               │                                               │
               │            ┌────────────────────┐             │
               │            │       User         │             │
               │            ├────────────────────┤             │
               │            │ id (UUID, PK)      │             │
               │            │ email (Unique)     │             │
               │            │ role (Choice)      │             │
               │            │ is_active, is_staff│             │
               │            └─────────┬──────────┘             │
               │                      │                        │
               │           ┌──────────┼──────────┐             │
               │       1:1 │      1:1 │      1:1 │             │
               │           ▼          │          ▼             │
               │  ┌────────────────┐  │  ┌────────────────┐    │
               │  │ PatientProfile │  │  │     Doctor     │    │
               │  ├────────────────┤  │  ├────────────────┤    │
               │  │ user (1:1 User)│  │  │ user (1:1 User)│    │
               │  │ gender, dob    │  │  │ name, name_ar  │    │
               │  │ blood_group    │  │  │ specialty      │    │
               │  │ allergies      │  │  │ hospital (FK) ◄─────┼──── Exclusive (OR)
               │  │ insurance_prov │  │  │ clinic (FK)   ◄─────┼──── Check Constraint
               │  │ insurance_num  │  │  │ status         │    │
               │  └───────┬────────┘  │  └───────┬────────┘    │
               │          │ 1:N       │          │ 1:1         │
               │          ▼           │          ▼             │
               │  ┌────────────────┐  │  ┌────────────────┐    │
               │  │PatientDependent│  │  │ DoctorSchedule │    │
               │  ├────────────────┤  │  ├────────────────┤    │
               │  │ profile (FK)   │  │  │ doctor (1:1)   │    │
               │  │ name, relation │  │  │ available_days │    │
               │  │ dob, blood_grp │  │  │ standard_slots │    │
               │  └────────────────┘  │  └────────────────┘    │
               │                      │                        │
               └──────────────────────┼────────────────────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │     Appointment     │
                           ├─────────────────────┤
                           │ id (UUID, PK)       │
                           │ patient (FK User)   │
                           │ doctor (FK Doctor)  │
                           │ hospital (FK, Opt)  │
                           │ clinic (FK, Opt)    │
                           │ date (Date)         │
                           │ time_slot (Char)    │
                           │ status (Choice)     │
                           │ cancel_reason, etc. │
                           └──────────┬──────────┘
                                      │
                         ┌────────────┴────────────┐
                     1:1 │                     1:1 │
                         ▼                         ▼
              ┌─────────────────────┐   ┌─────────────────────┐
              │    DoctorReview     │   │    Prescription     │
              ├─────────────────────┤   ├─────────────────────┤
              │ appointment (1:1)   │   │ appointment (1:1)   │
              │ doctor (FK Doctor)  │   │ doctor (FK Doctor)  │
              │ patient (FK User)   │   │ patient (FK User)   │
              │ rating (1 to 5)     │   │ diagnosis           │
              │ comment, created_at │   │ instructions        │
              └─────────────────────┘   └──────────┬──────────┘
                                                   │ 1:N
                                                   ▼
                                        ┌─────────────────────┐
                                        │PrescriptionMedicat'n│
                                        ├─────────────────────┤
                                        │ prescription (FK)   │
                                        │ medication_name     │
                                        │ dosage, frequency   │
                                        │ duration, instruc.  │
                                        └─────────────────────┘
```

---

## 8. Detailed Entity Specifications

### 8.1 `User` (Authentication & Core Identity)
- **Purpose:** Central authentication identity for all platform actors.
- **Fields:**
  - `id`: UUID (Primary Key, default `uuid.uuid4`).
  - `email`: `EmailField` (Unique, lowercase normalized, DB index).
  - `name`: `CharField(max_length=255)`.
  - `phone`: `CharField(max_length=32, blank=True)`.
  - `role`: `CharField(max_length=16, choices=['patient', 'doctor', 'hospital', 'admin'], default='patient', DB index)`.
  - `avatar`: `URLField(blank=True, null=True)`.
  - `is_active`: `BooleanField(default=True)`.
  - `is_staff`: `BooleanField(default=False)`.
  - `is_superuser`: `BooleanField(default=False)`.
  - `date_joined`: `DateTimeField(auto_now_add=True)`.
  - `last_login`: `DateTimeField(null=True, blank=True)`.
- **Indexes:** Index on `email`, `role`, `(role, is_active)`.
- **Sensitive Fields:** `password` (hashed).
- **Deletion Behavior:** `PROTECT` on associated operational records; soft-deactivation preferred (`is_active=False`).

### 8.2 `PatientProfile` & `PatientDependent` (Primary & Dependent Patients)
- **Conceptual Structure:**
  ```
  Account / User
  ├── Primary Patient (PatientProfile) ──► Appointments
  └── Dependent Patient (PatientDependent) ──► Appointments
  ```
- **Purpose:** Segregated clinical identities allowing both primary account holders and their dependents to maintain independent appointment histories and medical records, while the authorized account holder manages booking.
- **Fields (`PatientProfile` — Primary Patient):**
  - `id`: UUID (PK).
  - `user`: `OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')`.
  - `gender`: `CharField(max_length=16, choices=['male', 'female', 'other'], blank=True)`.
  - `dob`: `DateField(null=True, blank=True)`.
  - `blood_group`: `CharField(max_length=8, choices=['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'], blank=True)`.
  - `emergency_contact`: `CharField(max_length=64, blank=True)`.
  - `allergies`: `TextField(blank=True)`.
  - `insurance_provider`: `CharField(max_length=128, blank=True)`.
  - `insurance_number`: `CharField(max_length=64, blank=True)`.
- **Fields (`PatientDependent` — Dependent Patient):**
  - `id`: UUID (PK).
  - `profile`: `ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='dependents')`.
  - `name`: `CharField(max_length=255)`.
  - `relation`: `CharField(max_length=32, choices=['Spouse', 'Child', 'Parent', 'Sibling', 'Other'])`.
  - `gender`: `CharField(max_length=16, choices=['male', 'female', 'other'], blank=True)`.
  - `dob`: `DateField(null=True, blank=True)`.
  - `blood_group`: `CharField(max_length=8, blank=True)`.
  - `allergies`: `TextField(blank=True)`.
  - `medical_notes`: `TextField(blank=True)`.
  - `emergency_contact`: `CharField(max_length=64, blank=True)`.
  - `insurance_provider`: `CharField(max_length=128, blank=True)`.
  - `insurance_number`: `CharField(max_length=64, blank=True)`.
- **Authorization Scope:** Accessible and manageable exclusively by the parent account holder (`profile.user == request.user`).

### 8.3 `Hospital` & `FacilityDepartment`
- **Purpose:** Multi-specialty hospital facilities and departmental units.
- **Fields (`Hospital`):**
  - `id`: UUID (PK).
  - `admin_user`: `OneToOneField(User, on_delete=models.PROTECT, related_name='hospital_facility', null=True, blank=True)`.
  - `name`: `CharField(max_length=255)`.
  - `name_ar`: `CharField(max_length=255, blank=True)`.
  - `photo`: `URLField(blank=True)`.
  - `location`: `CharField(max_length=128)`.
  - `address`: `TextField()`.
  - `address_ar`: `TextField(blank=True)`.
  - `phone`: `CharField(max_length=32)`.
  - `operating_hours`: `CharField(max_length=128)`.
  - `operating_hours_ar`: `CharField(max_length=128, blank=True)`.
  - `about`: `TextField()`.
  - `about_ar`: `TextField(blank=True)`.
  - `emergency_available`: `BooleanField(default=False)`.
  - `status`: `CharField(max_length=16, choices=['Active', 'Deactivated'], default='Active', DB index)`.
- **Fields (`FacilityDepartment`):**
  - `id`: UUID (PK).
  - `hospital`: `ForeignKey(Hospital, on_delete=models.CASCADE, related_name='departments')`.
  - `name`: `CharField(max_length=128)`.
  - `head_of_department`: `CharField(max_length=255, blank=True)`.
  - `bed_capacity`: `PositiveIntegerField(default=0)`.
- **Derived Fields (Serialized):** `doctor_count` (computed dynamically via reverse relation count).

### 8.4 `Clinic`
- **Purpose:** Specialized outpatient medical centers.
- **Fields:**
  - `id`: UUID (PK).
  - `admin_user`: `OneToOneField(User, on_delete=models.PROTECT, related_name='clinic_facility', null=True, blank=True)`.
  - `name`: `CharField(max_length=255)`.
  - `name_ar`: `CharField(max_length=255, blank=True)`.
  - `photo`: `URLField(blank=True)`.
  - `location`: `CharField(max_length=128)`.
  - `address`: `TextField()`.
  - `address_ar`: `TextField(blank=True)`.
  - `primary_specialty`: `CharField(max_length=128)`.
  - `phone`: `CharField(max_length=32)`.
  - `operating_hours`: `CharField(max_length=128)`.
  - `operating_hours_ar`: `CharField(max_length=128, blank=True)`.
  - `about`: `TextField()`.
  - `about_ar`: `TextField(blank=True)`.
  - `status`: `CharField(max_length=16, choices=['Active', 'Deactivated'], default='Active', DB index)`.

### 8.5 `Doctor` & `DoctorSchedule`
- **Purpose:** Individual healthcare practitioner profile and consultation availability.
- **Fields (`Doctor`):**
  - `id`: UUID (PK).
  - `user`: `OneToOneField(User, on_delete=models.PROTECT, related_name='doctor_profile', null=True, blank=True)`.
  - `name`: `CharField(max_length=255)`.
  - `name_ar`: `CharField(max_length=255, blank=True)`.
  - `photo`: `URLField(blank=True)`.
  - `specialty`: `CharField(max_length=128, DB index)`.
  - `special_interests`: `JSONField(default=list, blank=True)`.
  - `experience_years`: `PositiveIntegerField(default=0)`.
  - `experience_text`: `CharField(max_length=64, blank=True)`.
  - `experience_text_ar`: `CharField(max_length=64, blank=True)`.
  - `hospital`: `ForeignKey(Hospital, on_delete=models.PROTECT, null=True, blank=True, related_name='doctors')`.
  - `clinic`: `ForeignKey(Clinic, on_delete=models.PROTECT, null=True, blank=True, related_name='doctors')`.
  - `location`: `CharField(max_length=128)`.
  - `about`: `TextField(blank=True)`.
  - `about_ar`: `TextField(blank=True)`.
  - `education`: `CharField(max_length=255, blank=True)`.
  - `consultation_fee`: `DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)`.
  - `rating`: `DecimalField(max_digits=3, decimal_places=2, default=5.00)`.
  - `review_count`: `PositiveIntegerField(default=0)`.
  - `status`: `CharField(max_length=16, choices=['Active', 'Deactivated'], default='Active', DB index)`.
- **Mandatory Exclusive Provider Constraint:**
  ```python
  constraints = [
      models.CheckConstraint(
          check=(
              models.Q(hospital__isnull=False, clinic__isnull=True) |
              models.Q(hospital__isnull=True, clinic__isnull=False)
          ),
          name='doctor_must_belong_to_hospital_xor_clinic'
      )
  ]
  ```
- **Fields (`DoctorSchedule`):**
  - `id`: UUID (PK).
  - `doctor`: `OneToOneField(Doctor, on_delete=models.CASCADE, related_name='schedule')`.
  - `available_days`: `JSONField(default=list)` (e.g. `["Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"]`).
  - `standard_slots`: `JSONField(default=list)` (e.g. `["09:00 - 09:30", "09:30 - 10:00", "10:00 - 10:30"]`).
  - `slot_duration_minutes`: `PositiveIntegerField(default=30)`.

### 8.6 `Appointment`
- **Purpose:** Patient consultation booking with doctor and facility, maintaining the distinction between the person receiving care (`patient`) and the account holder who booked (`booked_by`).
- **Fields:**
  - `id`: UUID (PK).
  - `booked_by`: `ForeignKey(User, on_delete=models.PROTECT, related_name='booked_appointments')` (the authenticated account holder who scheduled the visit).
  - `patient_profile`: `ForeignKey(PatientProfile, on_delete=models.PROTECT, null=True, blank=True, related_name='appointments')` (populated when the appointment is for the primary account holder).
  - `dependent`: `ForeignKey(PatientDependent, on_delete=models.PROTECT, null=True, blank=True, related_name='appointments')` (populated when the appointment is for a dependent patient).
  - `doctor`: `ForeignKey(Doctor, on_delete=models.PROTECT, related_name='appointments')`.
  - `hospital`: `ForeignKey(Hospital, on_delete=models.PROTECT, null=True, blank=True, related_name='appointments')`.
  - `clinic`: `ForeignKey(Clinic, on_delete=models.PROTECT, null=True, blank=True, related_name='appointments')`.
  - `patient_name_snapshot`: `CharField(max_length=255)` (snapshot of treated patient name).
  - `patient_phone_snapshot`: `CharField(max_length=32)` (snapshot of contact phone).
  - `patient_email_snapshot`: `EmailField()` (snapshot of booking confirmation email).
  - `specialty_snapshot`: `CharField(max_length=128)`.
  - `date`: `DateField(DB index)`.
  - `time_slot`: `CharField(max_length=32, DB index)`.
  - `status`: `CharField(max_length=16, choices=['pending', 'confirmed', 'completed', 'cancelled'], default='confirmed', DB index)`.
  - `notes`: `TextField(blank=True)`.
  - `cancel_reason`: `TextField(blank=True)`.
  - `cancelled_by_role`: `CharField(max_length=16, choices=['patient', 'doctor', 'hospital', 'admin'], blank=True)`.
  - `cancelled_by_user`: `ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cancelled_appointments')`.
  - `cancelled_at`: `DateTimeField(null=True, blank=True)`.
  - `created_at`: `DateTimeField(auto_now_add=True)`.
  - `updated_at`: `DateTimeField(auto_now=True)`.
- **Database Constraints:**
  ```python
  constraints = [
      # Authoritative active slot constraint preventing double booking
      models.UniqueConstraint(
          fields=['doctor', 'date', 'time_slot'],
          condition=models.Q(status__in=['confirmed', 'pending']),
          name='unique_active_doctor_slot'
      ),
      # Exclusive treated patient check: must be either primary patient OR dependent, never both, never neither
      models.CheckConstraint(
          check=(
              models.Q(patient_profile__isnull=False, dependent__isnull=True) |
              models.Q(patient_profile__isnull=True, dependent__isnull=False)
          ),
          name='appointment_must_have_primary_xor_dependent_patient'
      )
  ]
  ```
- **Historical Snapshot Rationale:** `hospital` / `clinic`, `patient_name_snapshot`, and `patient_phone_snapshot` are recorded at booking time to ensure historical accuracy if a doctor subsequently relocates or a patient updates their personal profile.

### 8.7 `Prescription` & `PrescriptionMedication`
- **Purpose:** Formal clinical consultation prescription and medication dosage records.
- **Fields (`Prescription`):**
  - `id`: UUID (PK).
  - `appointment`: `OneToOneField(Appointment, on_delete=models.PROTECT, related_name='prescription')`.
  - `doctor`: `ForeignKey(Doctor, on_delete=models.PROTECT, related_name='prescriptions')`.
  - `patient`: `ForeignKey(User, on_delete=models.PROTECT, related_name='prescriptions')`.
  - `diagnosis`: `TextField()`.
  - `instructions`: `TextField(blank=True)`.
  - `status`: `CharField(max_length=16, choices=['active', 'dispensed', 'cancelled'], default='active')`.
  - `issued_at`: `DateTimeField(auto_now_add=True)`.
- **Fields (`PrescriptionMedication`):**
  - `id`: UUID (PK).
  - `prescription`: `ForeignKey(Prescription, on_delete=models.CASCADE, related_name='medications')`.
  - `medication_name`: `CharField(max_length=255)`.
  - `dosage`: `CharField(max_length=128)` (e.g. "500 mg").
  - `frequency`: `CharField(max_length=128)` (e.g. "Twice daily after meals").
  - `duration`: `CharField(max_length=128)` (e.g. "7 days").
  - `instructions`: `TextField(blank=True)` (e.g. "Complete full course, avoid dairy").
- **Authorization Scope:** Strictly restricted to the attending doctor (`doctor.user == request.user`) and the owning patient (`patient == request.user`).

### 8.8 `DoctorReview`
- **Purpose:** Post-consultation verified patient feedback.
- **Fields:**
  - `id`: UUID (PK).
  - `appointment`: `OneToOneField(Appointment, on_delete=models.PROTECT, related_name='review')`.
  - `doctor`: `ForeignKey(Doctor, on_delete=models.CASCADE, related_name='reviews')`.
  - `patient`: `ForeignKey(User, on_delete=models.PROTECT, related_name='doctor_reviews')`.
  - `rating`: `PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])`.
  - `comment`: `TextField(blank=True)`.
  - `created_at`: `DateTimeField(auto_now_add=True)`.
- **Business Rules:**
  - Must only be created if `appointment.status == 'completed'`.
  - One review per completed appointment (enforced by `OneToOneField`).
  - Automatically updates `doctor.rating` and `doctor.review_count` atomically on creation.

### 8.9 `ProviderRequest` (Onboarding Application)
- **Purpose:** External partnership application from healthcare facilities.
- **Fields:**
  - `id`: UUID (PK).
  - `provider_type`: `CharField(max_length=16, choices=['hospital', 'clinic'])`.
  - `name`: `CharField(max_length=255)`.
  - `name_ar`: `CharField(max_length=255, blank=True)`.
  - `contact_person`: `CharField(max_length=255)`.
  - `contact_number`: `CharField(max_length=32)`.
  - `email`: `EmailField()`.
  - `country`: `CharField(max_length=64, default='United Arab Emirates')`.
  - `location`: `CharField(max_length=128)`.
  - `address`: `TextField(blank=True)`.
  - `status`: `CharField(max_length=16, choices=['pending', 'approved', 'rejected'], default='pending', DB index)`.
  - `admin_notes`: `TextField(blank=True)`.
  - `reviewed_by`: `ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_provider_requests')`.
  - `reviewed_at`: `DateTimeField(null=True, blank=True)`.
  - `submitted_at`: `DateTimeField(auto_now_add=True)`.

### 8.10 `ProviderInvitationToken` (Secure Onboarding Credential)
- **Purpose:** Cryptographically secure, single-use token for facility administrator password setup.
- **Fields:**
  - `id`: UUID (PK).
  - `user`: `OneToOneField(User, on_delete=models.CASCADE, related_name='invitation_token')`.
  - `token_hash`: `CharField(max_length=128, unique=True)` (SHA-256 hash of random token).
  - `expires_at`: `DateTimeField()`.
  - `is_used`: `BooleanField(default=False)`.
  - `created_at`: `DateTimeField(auto_now_add=True)`.

### 8.11 `Notification`
- **Purpose:** Persistent user notification inbox.
- **Fields:**
  - `id`: UUID (PK).
  - `user`: `ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')`.
  - `title`: `CharField(max_length=255)`.
  - `description`: `TextField()`.
  - `notification_type`: `CharField(max_length=32, choices=['appointment', 'prescription', 'reminder', 'system'])`.
  - `link`: `CharField(max_length=255, blank=True)`.
  - `is_read`: `BooleanField(default=False, DB index)`.
  - `created_at`: `DateTimeField(auto_now_add=True)`.

### 8.12 `AuditLog`
- **Purpose:** Immutable administrative compliance ledger.
- **Fields:**
  - `id`: `BigAutoField(PK)`.
  - `actor`: `ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_actions')`.
  - `action`: `CharField(max_length=64, DB index)`.
  - `target_model`: `CharField(max_length=64)`.
  - `target_id`: `CharField(max_length=64)`.
  - `change_summary`: `JSONField(default=dict)`.
  - `ip_address`: `GenericIPAddressField(null=True, blank=True)`.
  - `user_agent`: `CharField(max_length=255, blank=True)`.
  - `created_at`: `DateTimeField(auto_now_add=True, DB index)`.
- **Strict Data Minimization Policy:**
  - **Explicitly Forbidden:** Never stores passwords, hashes, raw JWTs, refresh tokens, invitation setup tokens, clinical diagnoses, prescriptions, consultation notes, or unnecessary PII (such as patient national IDs or emergency contact phone numbers).
  - **Security Purpose for Actor Email & IP:** Required exclusively for administrative accountability, non-repudiation, and fraud/intrusion detection on high-risk operations (e.g. facility approval, doctor deactivation).
  - **Retention Strategy:** Primary operational database retains records for a rolling **90-day window**; records older than 90 days are archived to encrypted cold storage with a **1-year compliance retention limit**, followed by permanent automated purging.

---

## 9. Appointment Concurrency & Double-Booking Prevention Strategy

Double-booking poses severe operational and patient care risks. MeetAdr implements an **authoritative database constraint backed by an application validation workflow**.

```
Request A (Patient 1)                         Request B (Patient 2)
Both select Dr. Tariq, 2026-09-26, 10:00 AM concurrently
         │                                             │
         ▼                                             ▼
Enter transaction.atomic()                    Enter transaction.atomic()
         │                                             │
Pre-check slot availability:                  Pre-check slot availability:
(Both see slot as initially open)             (Both see slot as initially open)
         │                                             │
Attempt INSERT into Appointment               Attempt INSERT into Appointment
         │                                             │
Transaction A Commits First                   Transaction B Attempts Commit
         │                                             │
PostgreSQL Unique Index:                      PostgreSQL Unique Index:
Validates (doctor, date, time_slot, active)   Collision Detected!
Index row inserted successfully.              IntegrityError raised by PostgreSQL!
         │                                             │
         ▼                                             ▼
Transaction A Committed                       Transaction B Rolls Back
HTTP 201 Created Returned                     Catches IntegrityError
                                              HTTP 409 Conflict Returned:
                                              "SLOT_ALREADY_BOOKED"
```

### 9.1 The Authoritative Foundation: PostgreSQL Unique Partial Constraint

The single authoritative protection against double booking is the PostgreSQL partial unique index:
```python
models.UniqueConstraint(
    fields=['doctor', 'date', 'time_slot'],
    condition=models.Q(status__in=['confirmed', 'pending']),
    name='unique_active_doctor_slot'
)
```
- **Why this is authoritative:** PostgreSQL's B-Tree index guarantees uniqueness at storage engine commit time. No amount of application-level race conditions, distributed API workers, or concurrent requests can violate this constraint.
- **Evaluation of Locking Strategy:**
  - `Doctor.objects.select_for_update()` locks the parent `Doctor` row across **all dates and slots**. Locking the whole doctor creates severe lock contention, serializing completely unrelated bookings (e.g. Monday 9 AM vs Friday 3 PM).
  - Therefore, the system utilizes targeted application checks followed by the authoritative PostgreSQL unique constraint. If serialized locking is ever needed in extreme high-contention bursts, it is applied to specific slot keys (e.g., via advisory locks on `hash(doctor_id, date, time_slot)`), avoiding global table or row bottlenecks.
- **Application Booking Workflow:**
```python
from django.db import transaction, IntegrityError
from rest_framework.exceptions import ValidationError

@transaction.atomic
def create_appointment_service(patient_user, doctor_id, date, time_slot, notes=""):
    # 1. Fetch doctor and verify active status
    try:
        doctor = Doctor.objects.get(id=doctor_id, status='Active')
    except Doctor.DoesNotExist:
        raise ValidationError("Doctor does not exist or is currently inactive.")

    # 2. Verify doctor belongs to an active facility
    facility = doctor.hospital or doctor.clinic
    if not facility or facility.status != 'Active':
        raise ValidationError("The doctor's affiliated facility is currently inactive.")

    # 3. Verify requested date matches practicing days
    weekday_name = date.strftime('%A')
    if weekday_name not in doctor.schedule.available_days:
        raise ValidationError(f"Dr. {doctor.name} does not practice on {weekday_name}s.")

    # 4. Verify time slot is in doctor's configured schedule
    if time_slot not in doctor.schedule.standard_slots:
        raise ValidationError("The requested time slot is not within the doctor's standard schedule.")

    # 5. Pre-check for existing active appointment (fail fast for normal UX)
    conflict = Appointment.objects.filter(
        doctor=doctor,
        date=date,
        time_slot=time_slot,
        status__in=['confirmed', 'pending']
    ).exists()
    
    if conflict:
        raise ConflictError(
            code="SLOT_ALREADY_BOOKED",
            message=f"The selected time slot ({time_slot}) with Dr. {doctor.name} has already been booked."
        )

    # 6. Create appointment protected by PostgreSQL unique constraint
    try:
        appointment = Appointment.objects.create(
            patient=patient_user,
            doctor=doctor,
            hospital=doctor.hospital,
            clinic=doctor.clinic,
            patient_name_snapshot=patient_user.name,
            patient_phone_snapshot=patient_user.phone or "",
            patient_email_snapshot=patient_user.email,
            specialty_snapshot=doctor.specialty,
            date=date,
            time_slot=time_slot,
            status='confirmed',
            notes=notes
        )
        return appointment
    except IntegrityError:
        # Authoritative catch when a concurrent transaction won the commit race
        raise ConflictError(
            code="SLOT_ALREADY_BOOKED",
            message=f"The selected time slot ({time_slot}) has just been booked by another patient."
        )
```

### 9.2 Concurrency Verification Test Specification
A dedicated multi-threaded stress test will be executed:
- **Test:** Spawn 10 concurrent threads targeting the exact same `(doctor_id, date, time_slot)`.
- **Expected Outcome:** **Exactly one active appointment exists for the same doctor/date/time slot.** Other concurrent requests receive an appropriate documented conflict (`409 Conflict`) or throttle (`429 Too Many Requests`) response.

---

## 10. Provider Onboarding & Credential Lifecycle

Provider registration must be secure, fraud-resistant, and entirely free of plaintext password transmission.

```
Step 1: Public Submission
   Public applicant fills /join wizard
   ──► POST /api/v1/provider-requests/
   ──► Stores ProviderRequest (Status: 'pending')

Step 2: Superadmin Review & Approval
   Admin reviews application at /admin/requests
   ──► PATCH /api/v1/admin/requests/{id}/status/ {"status": "approved"}
   ──► Server executes provisioning within atomic transaction:
       1. Creates Hospital or Clinic (Status: 'Deactivated')
       2. Creates facility admin User (role='hospital', is_active=False, unusable password)
       3. Generates cryptographically secure, random 64-character token
       4. Stores SHA-256 hash in ProviderInvitationToken (Expires in 72 hours)
       5. Triggers invitation email dispatch with one-time setup link

Step 3: Administrator Invitation & Password Setup
   Administrator receives link: https://meetadr.com/provider-setup?token=<raw_token>
   ──► POST /api/v1/auth/provider-setup/validate/ {"token": "..."}
       (Verifies token exists, unexpired, and unused)
   ──► POST /api/v1/auth/provider-setup/complete/ {"token": "...", "password": "..."}
       (Validates password strength, sets user password, marks token is_used=True, sets user is_active=True)

Step 4: Facility Activation
   Facility status transitions to 'Active' upon completing setup and operational inspection.
```

---

## 11. API Architecture & Endpoint Specification

Base URL: `/api/v1/`

### 11.1 Authentication (`/api/v1/auth/`)
- `POST /api/v1/auth/login/`: Email + password authentication. Sets HttpOnly refresh cookie, returns access token + user profile.
- `POST /api/v1/auth/register/`: Patient self-registration. Defaults strictly to `role='patient'`.
- `POST /api/v1/auth/token/refresh/`: Refreshes access token via HttpOnly cookie; rotates refresh token.
- `GET /api/v1/auth/me/`: Returns authenticated user profile and associated metadata.
- `POST /api/v1/auth/logout/`: Blacklists refresh token; clears cookie.
- `POST /api/v1/auth/provider-setup/validate/`: Validates invitation setup token.
- `POST /api/v1/auth/provider-setup/complete/`: Sets password for newly approved facility administrator.

### 11.2 Healthcare Directory & Public Discovery (`/api/v1/`)
- `GET /api/v1/doctors/`: Filterable doctor directory (specialty, location, hospital, clinic, keyword, practicing day).
- `GET /api/v1/doctors/{id}/`: Doctor profile details with reviews and affiliated facility info.
- `GET /api/v1/doctors/{id}/availability/?date=YYYY-MM-DD`: Available days and 30-min consultation slots calculation.
- `GET /api/v1/hospitals/`: Hospital directory with location and emergency status filtering.
- `GET /api/v1/hospitals/{id}/`: Comprehensive hospital profile with departments and affiliated doctors.
- `GET /api/v1/clinics/`: Specialized clinic directory.
- `GET /api/v1/clinics/{id}/`: Clinic profile with affiliated doctors roster.
- `GET /api/v1/specialties/`: Standard medical specialties list.
- `GET /api/v1/conditions/`: Medical conditions A-Z index with symptoms and specialty mappings.
- `POST /api/v1/provider-requests/`: Public provider partnership application.

### 11.3 Appointments & Consultations (`/api/v1/appointments/`)
- `POST /api/v1/appointments/`: Concurrency-safe appointment creation for authenticated patient.
- `GET /api/v1/appointments/my/`: History and upcoming appointments for authenticated patient.
- `GET /api/v1/appointments/{id}/`: Single appointment inspection (enforces ownership).
- `POST /api/v1/appointments/{id}/cancel/`: Appointment cancellation with audit reason and role recording.
- `POST /api/v1/appointments/{id}/complete/`: Mark consultation completed (Doctor only).
- `POST /api/v1/appointments/{id}/review/`: Submit 1-5 star review for completed appointment (Patient only).

### 11.4 Prescriptions (`/api/v1/prescriptions/`)
- `GET /api/v1/prescriptions/my/`: Patient's issued digital prescriptions list.
- `GET /api/v1/prescriptions/{id}/`: Single prescription details with medication items.
- `POST /api/v1/prescriptions/`: Create structured prescription for appointment (Attending Doctor only).

### 11.5 Patient Portal (`/api/v1/patient/`)
- `GET /api/v1/patient/profile/`: Patient medical profile, allergies, insurance.
- `PUT/PATCH /api/v1/patient/profile/`: Update patient medical profile.
- `GET /api/v1/patient/dependents/`: List patient dependents.
- `POST /api/v1/patient/dependents/`: Add dependent.
- `DELETE /api/v1/patient/dependents/{id}/`: Remove dependent.

### 11.6 Doctor Portal (`/api/v1/doctor/`)
- `GET /api/v1/doctor/dashboard/`: Doctor KPI metrics (completion rate, status counts).
- `GET /api/v1/doctor/appointments/`: Doctor's consultations list.
- `GET /api/v1/doctor/schedule/`: Doctor's active practicing days and slot configuration.
- `PUT/PATCH /api/v1/doctor/schedule/`: Update doctor's active practicing days and slot configuration.
- `GET /api/v1/doctor/patients/`: Patients treated by this doctor (derived from appointments).

### 11.7 Hospital & Clinic Portal (`/api/v1/hospital/` & `/api/hospital-admin/`)
- `GET /api/v1/hospital/dashboard/`: Facility metrics, doctor utilization, appointment breakdown.
- `GET /api/v1/hospital/doctors/`: List doctors belonging ONLY to authenticated facility.
- `POST /api/v1/hospital/doctors/`: Add new doctor to facility roster.
- `PATCH /api/v1/hospital/doctors/{id}/status/`: Toggle doctor Active/Deactivated for this facility.
- `GET /api/v1/hospital/departments/`: List clinical departments for this hospital.
- `POST /api/v1/hospital/departments/`: Add clinical department to this hospital.
- `GET /api/v1/hospital/settings/`: Facility operational settings and emergency status.
- `PUT/PATCH /api/v1/hospital/settings/`: Update facility operational settings.
- `POST /api/hospital-admin/appointments/{appointment_id}/cancel/` (Alias: `POST /api/v1/hospital/appointments/{id}/cancel/`):
  - **Purpose:** Enables hospital/clinic administrators to cancel appointments for affiliated doctors when emergencies or doctor absences occur.
  - **Payload:** `{"reason": "Doctor unavailable"}`
  - **Verification & Execution Pipeline:**
    1. Administrator is authenticated.
    2. User has the appropriate hospital/clinic administrator role (`role == 'hospital'`).
    3. The appointment belongs to a doctor associated with that administrator's facility (`doctor.hospital == admin_facility` or `doctor.clinic == admin_facility`). Cross-facility cancellations are rejected (`404 Not Found`).
    4. The appointment is currently in a cancellable state (`confirmed` or `pending`).
    5. The appointment is marked as `cancelled` (never deleted).
    6. The cancellation reason is recorded (`cancel_reason = data['reason']`).
    7. The cancelling administrator and cancellation timestamp are recorded (`cancelled_by_role = 'hospital'`, `cancelled_by_user = request.user`, `cancelled_at = timezone.now()`).
    8. The booked slot is released automatically (PostgreSQL unique partial index only constraints active `confirmed` / `pending` states).
    9. The patient notification workflow is triggered (system creates a notification for `appointment.booked_by`).

### 11.8 Admin Oversight Portal (`/api/v1/admin/`)
- `GET /api/v1/admin/dashboard/`: Platform-wide analytics and audit activity stream.
- `GET /api/v1/admin/doctors/`: Platform-wide doctor list with status filtering.
- `PATCH /api/v1/admin/doctors/{id}/status/`: Activate or deactivate any doctor.
- `GET /api/v1/admin/providers/`: Platform-wide hospital and clinic list.
- `PATCH /api/v1/admin/providers/{id}/status/`: Activate or deactivate any hospital or clinic.
- `GET /api/v1/admin/bookings/`: Global appointment inspector with administrative cancellation action.
- `GET /api/v1/admin/requests/`: Provider onboarding applications list.
- `PATCH /api/v1/admin/requests/{id}/status/`: Approve or reject onboarding application.
- `GET /api/v1/admin/reports/`: Aggregated reports by doctor, specialty, facility with rolling timeframes.

### 11.9 Notifications (`/api/v1/notifications/`)
- `GET /api/v1/notifications/`: List notifications for authenticated user.
- `PATCH /api/v1/notifications/{id}/read/`: Mark notification as read.

---

## 12. Serialization & Normalization Strategy

To ensure high performance and eliminate data redundancy, database tables remain fully normalized while serializers handle frontend contracts:

1. **Doctor Count:**
   - **Frontend Expectation:** `Hospital.doctorCount`, `Clinic.doctorCount`.
   - **Database Reality:** Computed dynamically using Django `annotate(doctor_count=Count('doctors', filter=Q(doctors__status='Active')))`.
2. **Reverse Doctor Lists:**
   - **Frontend Mock Data:** `Hospital.doctorIds = ['doc_1', 'doc_2']`.
   - **Database Reality:** Replaced with relational foreign keys `Doctor.hospital` and `Doctor.clinic`. Serializer provides dynamic IDs when required by legacy consumers.
3. **Facility Name Snapshot:**
   - Appointments serialize `providerName`, `facilityName`, and `hospitalName` seamlessly from related `hospital` / `clinic` objects without maintaining triple redundant string columns.
4. **Bilingual Presentation:**
   - Serializers expose both English and Arabic attributes (`name`, `nameAr`, `address`, `addressAr`, `about`, `aboutAr`) matching frontend TypeScript interfaces directly.

---

## 13. Error Handling Architecture

A uniform, structured error payload is enforced across all API responses via a custom DRF exception handler:

### Standard Error Payload
```json
{
  "error": "ConflictError",
  "message": "The selected time slot (10:00 AM) with Dr. Tariq Al-Mansoor has already been booked.",
  "code": "SLOT_ALREADY_BOOKED",
  "details": {}
}
```

### Standard Error Code Registry
| HTTP Status | Error Type | Error Code | Description |
|---|---|---|---|
| `400 Bad Request` | `ValidationError` | `INVALID_INPUT` | Malformed input or validation error |
| `401 Unauthorized` | `AuthenticationError` | `AUTH_REQUIRED` | Missing or invalid access token |
| `401 Unauthorized` | `AuthenticationError` | `TOKEN_EXPIRED` | Access token has expired |
| `403 Forbidden` | `PermissionDenied` | `PERMISSION_DENIED` | Authenticated user lacks permission |
| `404 Not Found` | `NotFoundError` | `RESOURCE_NOT_FOUND` | Resource does not exist or access denied |
| `409 Conflict` | `ConflictError` | `SLOT_ALREADY_BOOKED` | Concurrent appointment slot collision |
| `409 Conflict` | `ConflictError` | `DUPLICATE_APPLICATION`| Provider request already pending |
| `429 Too Many Requests`| `ThrottledError`| `RATE_LIMIT_EXCEEDED` | API rate limit exceeded |
| `500 Server Error` | `InternalError` | `INTERNAL_SERVER_ERROR`| Production server exception (no stack trace leaked) |

---

## 14. Testing Architecture & Matrix

The backend verification plan covers 18 distinct test domains:
1. **Authentication & Password Policy:** Login, token refresh, token rotation, logout blacklisting, and full Django password validators suite (similarity, min length 10, common password dictionary, numeric check, character complexity).
2. **Role Boundaries:** Preventing patients from accessing doctor/hospital/admin endpoints.
3. **Privilege Escalation:** Verifying that `role="admin"` sent during patient registration is discarded.
4. **Provider Isolation (Hospital):** Proving Hospital A cannot read or modify Hospital B doctors, departments, or appointments.
5. **Provider Isolation (Clinic):** Proving Clinic A cannot access Clinic B data.
6. **Patient Data Isolation:** Verifying Patient A cannot access Patient B profiles, appointments, or prescriptions.
7. **Doctor Data Isolation:** Verifying Doctor A cannot view Doctor B private schedule or appointments.
8. **Double-Booking Race Condition:** Multi-threaded concurrency test proving **exactly one active appointment exists for the same doctor/date/time slot**, with all other concurrent requests receiving an appropriate conflict (409) or throttle (429) response.
9. **Doctor Availability Calculation:** Validating accurate exclusion of booked slots and respecting practicing days.
10. **Appointment Lifecycle State Machine:** Enforcing valid transitions (`pending` → `confirmed` → `completed` / `cancelled`).
11. **Appointment Cancellation Tracking:** Verifying cancellation reasons and tracking cancelling actor.
12. **Prescription Confidentiality:** Ensuring only attending doctor and owning patient can access prescriptions.
13. **Doctor Review Constraints:** Verifying reviews can only be submitted for completed appointments, exactly once.
14. **Provider Onboarding Lifecycle:** Request creation → admin approval → facility deactivated → invitation token generation → password setup → activation.
15. **Superadmin Verification:** Admin status toggling of doctors and facilities with immutable audit logging.
16. **Input Validation:** Rejection of malicious payloads, invalid UUIDs, bad date formats, SQL injection patterns.
17. **API Rate Limiting:** Verification of throttling on login, registration, and booking endpoints.
18. **CORS & CSRF:** Rejection of untrusted origins and validation of CSRF tokens on cookie-based refresh endpoints.
