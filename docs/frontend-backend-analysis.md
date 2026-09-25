# MeetAdr Frontend-to-Backend Architecture & Requirement Audit
**Document ID:** `MEETADR-PHASE0-AUDIT`  
**Date:** September 24, 2026  
**Auditor:** Backend Architecture Agent  
**Scope:** Complete Read-Only Audit of `meetadr/frontend/src`  

---

## 1. Frontend Routes Overview

| Route | Access / Role Protection | Associated Component | Description |
|---|---|---|---|
| `/` | Public | `Home` | Master landing page with accredited hero search, sliding specialties, partner hospitals, FAQ, trust metrics |
| `/search` | Public | `SearchPage` | Consolidated unified search across Doctors, Hospitals, and Clinics with faceted filtering |
| `/doctors` | Public | `DoctorList` | Doctor directory filtering by specialty, location (with GPS auto-detect), and keywords |
| `/doctors/:id` | Public | `DoctorDetails` | Individual doctor profile, hospital affiliation, reviews, and direct booking CTA |
| `/hospitals` | Public | `HospitalList` | Public hospital listing with search and location filtering |
| `/hospitals/:id` | Public | `HospitalDetails` | Comprehensive hospital profile, departments, accredited doctors roster, and contact |
| `/clinics` | Public | `ClinicList` | Specialized clinic directory with specialty & keyword filtering |
| `/clinics/:id` | Public | `ClinicDetails` | Clinic facility profile and affiliated doctors |
| `/specialties` | Public | `SpecialtiesPage` | Browse healthcare services by specialty categories |
| `/conditions` | Public | `ConditionsPage` | A-Z Directory of medical conditions, symptoms, and matching specialties |
| `/diseases` | Public (Redirect) | `Navigate -> /conditions` | Alias redirect to `/conditions` |
| `/waitlist` | Public (Redirect) | `Navigate -> /` | Alias redirect to home |
| `/join`, `/become-a-partner`, `/provider-register` | Public | `JoinProviderPage` | 3-step onboarding wizard for Hospitals and Clinics to request platform partnership |
| `/about`, `/services`, `/partners`, `/contact`, `/faq`, `/help`, `/privacy`, `/terms`, `/accessibility`, `/careers`, `/refer` | Public | `StaticPages` | Informational, compliance, and support content |
| `/book` | Public / Patient | `BookingPage` | Master appointment booking console with multi-specialty selector and dynamic slot calendar |
| `/book/doctor/:doctorId` | Public / Patient | `BookingPage` | Pre-selected doctor booking flow |
| `/login`, `/:role/login` | Public | `LoginPage` | Authentication entry point for all roles (Patient, Doctor, Hospital, Admin) |
| `/patient/*` | Protected (`patient`) | `PatientLayout` | Patient portal root layout |
| `/patient/dashboard` | Protected (`patient`) | `PatientDashboard` | Upcoming visits, health metrics, recent bookings, countdown timers, review triggers |
| `/patient/profile` | Protected (`patient`) | `PatientProfile` | Personal details, emergency contacts, blood group, allergies, insurance, dependents |
| `/patient/bookings` | Protected (`patient`) | `PatientBookings` | Appointment history, cancellation modal, rating modal, prescription status |
| `/doctor/*` | Protected (`doctor`) | `DashboardLayout` (`doctor`) | Doctor portal root layout |
| `/doctor/dashboard` | Protected (`doctor`) | `DoctorDashboard` | Doctor metrics (completed, cancelled, confirmed), workload charts, patient list, complete/cancel actions |
| `/doctor/schedule` | Protected (`doctor`) | `DoctorSchedule` | Practicing days selection & 30-min consultation slot availability configuration |
| `/doctor/patients` | Protected (`doctor`) | `DoctorPatients` | Patient directory derived from past/upcoming appointments for that doctor |
| `/hospital/*` | Protected (`hospital`) | `DashboardLayout` (`hospital`)| Hospital/Clinic portal root layout |
| `/hospital/dashboard` | Protected (`hospital`) | `HospitalDashboard` | Facility metrics, doctor utilization, appointment breakdown, quick actions |
| `/hospital/doctors` | Protected (`hospital`) | `HospitalDoctors` | Facility doctor management (add doctor to roster, activate/deactivate, roster table/cards) |
| `/hospital/departments` | Protected (`hospital`) | `HospitalDepartments` | Facility department & clinical unit management (head of dept, bed capacity, doctor count) |
| `/hospital/settings` | Protected (`hospital`) | `HospitalSettings` | Operational configuration (facility name, emergency readiness, operating hours, address, phone) |
| `/admin/*` | Protected (`admin`) | `DashboardLayout` (`admin`) | Superadmin management portal |
| `/admin/dashboard` | Protected (`admin`) | `AdminDashboard` | Platform analytics, total users/providers/bookings, status distribution, recent audit log |
| `/admin/doctors` | Protected (`admin`) | `AdminDoctors` | Platform-wide doctor verification and activation/deactivation |
| `/admin/providers` | Protected (`admin`) | `AdminProviders` | Platform-wide hospital and clinic facility management (verification and activation/deactivation) |
| `/admin/bookings` | Protected (`admin`) | `AdminBookings` | Global appointment inspection, status filtering, administrative cancellations |
| `/admin/requests` | Protected (`admin`) | `AdminRequests` | Provider onboarding applications review (Approve / Reject hospital and clinic requests) |
| `/admin/reports` | Protected (`admin`) | `AdminReports` | Platform analytics reports (by doctor, specialty, facility, daily/weekly/monthly aggregation, JSON export) |

---

## 2. User Roles & Permission Matrix

The system specifies **4 distinct roles**:

```
                 ┌────────────────────────────────────────────────┐
                 │                 meetAdr Roles                  │
                 └──────────────────────┬─────────────────────────┘
                                        │
        ┌───────────────────┬───────────┴───────────┬───────────────────┐
        ▼                   ▼                       ▼                   ▼
    [ patient ]         [ doctor ]             [ hospital ]         [ admin ]
   - Self profile      - Own profile          - Own facility       - Platform oversight
   - Search & book     - Own schedule         - Own doctors only   - Verify providers
   - Cancel own appt   - Own consultations    - Own departments    - Activate/deactivate
   - Submit reviews    - Own patient records  - Own analytics      - System analytics
```

### Authorization Boundaries:
1. **Patient:**
   - Can read public directories (`Doctor`, `Hospital`, `Clinic`, `Specialty`, `Condition`).
   - Can create appointments for themselves.
   - Can read and cancel ONLY their own appointments.
   - Can read/update ONLY their own patient profile and dependents.
   - Can submit reviews ONLY for completed appointments belonging to them.
   - Cannot access doctor schedule editor, hospital management, or admin console.

2. **Doctor:**
   - Linked to a `Doctor` record via `user.doctorId` and assigned to a `Hospital` (`user.hospitalId`) or `Clinic` (`user.clinicId`).
   - Can read and update ONLY their own practicing days and slot schedules.
   - Can view and manage ONLY appointments assigned to their `doctorId`.
   - Can mark consultations as `completed` or `cancelled`.
   - Can view patient history ONLY for patients who have booked consultations with them.
   - Cannot view or edit other doctors' private data, appointments, or schedules.

3. **Hospital / Clinic Provider:**
   - Represents the administrative account for an onboarded facility (`user.hospitalId` or `user.clinicId`).
   - Can manage ONLY doctors belonging to their specific facility.
   - Can manage departments/clinical units of their own facility.
   - Can update operational settings (emergency status, operating hours, contact) of their own facility.
   - Can view appointments booked at their facility.
   - CANNOT access, edit, or view records belonging to any competing hospital or clinic.

4. **Admin:**
   - Platform superuser.
   - Can approve/reject `ProviderRequest` onboarding applications.
   - Can toggle `Active` / `Deactivated` status for any Hospital, Clinic, or Doctor.
   - Can view global appointment logs and execute administrative cancellations with audit reasons.
   - Can view platform-wide business analytics and export audit reports.

---

## 3. Authentication Requirements

### Current Frontend Implementation:
- Authenticates via **Email + Password**.
- Guest booking flow in `BookingPage.tsx` includes an email login form, a mobile OTP simulation (demo code `1234`), and a one-click demo login.
- `AuthContext` stores the user session in `localStorage` under `meetadr_session_v3`.
- No real tokens currently exist in the frontend mock service; user objects are stored in raw JSON format.

### Target Backend Authentication Blueprint:
- **Protocol:** RESTful token-based authentication using **JWT (JSON Web Tokens)** via `djangorestframework-simplejwt` or secure HTTP-only cookies.
- **Why JWT?**
  - Stateless token architecture pairs naturally with the detached React SPA.
  - Short-lived Access Token (e.g., 15 minutes) prevents replay if intercepted.
  - Long-lived Refresh Token (e.g., 7 days) stored securely with token rotation and blacklisting on logout.
- **Password Security:** Django `PBKDF2PasswordHasher` or `Argon2` with strict strength validation.
- **Server-Controlled Roles:** The registration endpoint must default to `role="patient"`. Under no circumstances can a registration payload specify `role="admin"` or `role="hospital"`. Staff accounts must be provisioned either through the admin panel or through approved `ProviderRequest` onboarding.

---

## 4. User Entity (Core Auth)

Frontend TypeScript definition (`frontend/src/types/index.ts`):
```typescript
export type UserRole = 'patient' | 'doctor' | 'hospital' | 'admin';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  mobile?: string;
  phone?: string;
  hospitalId?: string;
  doctorId?: string;
  avatar?: string;
}
```

### Proposed Backend Model (`User` extending `AbstractBaseUser` + `PermissionsMixin`):
- `id` (UUID / BigAutoField)
- `email` (EmailField, unique, indexed)
- `name` (CharField, max_length=255)
- `role` (CharField, choices: `patient`, `doctor`, `hospital`, `admin`, default=`patient`, indexed)
- `mobile` / `phone` (CharField, max_length=32, blank=True)
- `avatar` (URLField or ImageField, blank=True)
- `is_active` (BooleanField, default=True)
- `is_staff` (BooleanField, default=False)
- `date_joined` (DateTimeField, auto_now_add=True)
- `last_login` (DateTimeField, blank=True, null=True)

---

## 5. Hospital Entity

Frontend TypeScript definition (`frontend/src/types/index.ts`):
```typescript
export interface Hospital {
  id: string;
  name: string;
  nameAr?: string;
  photo: string;
  location: string;
  address: string;
  addressAr?: string;
  specialties: string[];
  doctorIds: string[];
  doctorCount: number;
  rating: number;
  emergencyAvailable: boolean;
  phone: string;
  operatingHours: string;
  operatingHoursAr?: string;
  about: string;
  aboutAr?: string;
  status?: 'Active' | 'Deactivated';
}
```

### Key Business Insights:
- Public hospitals are major accredited medical complexes (e.g., CityCare, American Hospital, Al-Zahra).
- They have a bilingual presence (`name`, `nameAr`, `addressAr`, `operatingHoursAr`, `aboutAr`).
- Contains facility operational flags: `emergencyAvailable` (24/7 ER availability), `status` ('Active' | 'Deactivated').
- Has an associated `admin_user` (ForeignKey or OneToOne to `User` with `role='hospital'`).
- In relational schema, `doctorIds` and `doctorCount` should NOT be static stored arrays; they are computed dynamically via reverse relations from `Doctor`.

---

## 6. Clinic Entity

Frontend TypeScript definition (`frontend/src/types/index.ts`):
```typescript
export interface Clinic {
  id: string;
  name: string;
  photo: string;
  location: string;
  address: string;
  specialty: string;
  doctorIds: string[];
  doctorCount: number;
  rating: number;
  phone: string;
  operatingHours: string;
  about: string;
  status?: 'Active' | 'Deactivated';
}
```

### Business Distinction vs Hospital:
- A Clinic is a specialized outpatient medical center focusing on a primary specialty (e.g., Dental Clinic, Dermatology Center, Day Surgery).
- Distinct from Hospital (does not have multi-specialty emergency centers or bed wards).
- Has its own management access or clinic manager account.

---

## 7. Doctor Entity

Frontend TypeScript definition (`frontend/src/types/index.ts`):
```typescript
export interface Doctor {
  id: string;
  name: string;
  nameAr?: string;
  photo: string;
  specialty: string;
  specialInterest?: string[];
  experience: string;
  experienceAr?: string;
  rating: number;
  reviewCount: number;
  location: string;
  hospitalId?: string;
  clinicId?: string;
  hospitalName?: string;
  hospitalNameAr?: string;
  clinicName?: string;
  about: string;
  aboutAr?: string;
  education: string;
  availableDays: string[];
  availableSlots: string[];
  consultationFee?: number;
  status?: 'Active' | 'Deactivated';
}
```

### Mandatory Structural Rules:
- **CRITICAL BUSINESS RULE:** Individual doctors are NOT independent providers. Every doctor belongs to a **Hospital** (`hospitalId`) OR a **Clinic** (`clinicId`).
- A database check constraint must guarantee that `hospital_id` OR `clinic_id` is populated, but a doctor cannot belong to mismatched unrelated providers.
- Link to User account: Doctor profile connects to a `User` account (`role='doctor'`) via `OneToOneField(User, null=True, blank=True)`.

---

## 8. Patient Entity & Medical Profile

Frontend TypeScript definition (`frontend/src/types/index.ts` + `PatientProfile.tsx`):
```typescript
export interface Patient {
  id: string;
  name: string;
  email: string;
  mobile: string;
  phone?: string;
  gender: string;
  age: number;
  bloodGroup: string;
}
```
Plus additional patient profile fields in `PatientProfile.tsx`:
- `emergencyContact`: string
- `allergies`: string
- `insuranceProvider`: string
- `insuranceNumber`: string
- `dependents`: Array of `{ id, name, relation, dob, bloodGroup }`

### Proposed Backend Patient Models:
1. **`PatientProfile`**: `OneToOneField(User, on_delete=CASCADE)`
   - `gender` (CharField)
   - `dob` (DateField) / `age`
   - `blood_group` (CharField: A+, A-, B+, B-, AB+, AB-, O+, O-)
   - `emergency_contact` (CharField)
   - `allergies` (TextField, blank=True)
   - `insurance_provider` (CharField, blank=True)
   - `insurance_number` (CharField, blank=True)
2. **`PatientDependent`**: `ForeignKey(PatientProfile, related_name='dependents')`
   - `name` (CharField)
   - `relation` (CharField: Spouse, Child, Parent, Sibling, Other)
   - `dob` (DateField)
   - `blood_group` (CharField)

---

## 9. Appointment / Booking Entity

Frontend TypeScript definition (`frontend/src/types/index.ts` & `BookingPage.tsx`):
```typescript
export interface Appointment {
  id: string;
  patientId: string;
  patientName: string;
  patientMobile: string;
  patientPhone?: string;
  patientEmail?: string;
  doctorId: string;
  doctorName: string;
  doctorPhoto?: string;
  hospitalId?: string;
  clinicId?: string;
  providerName: string;
  facilityName?: string;
  hospitalName?: string;
  specialty: string;
  location: string;
  date: string; // YYYY-MM-DD
  time: string; // e.g. "10:00 AM"
  timeSlot?: string;
  status: 'Confirmed' | 'Cancelled' | 'Completed' | 'Pending' | 'confirmed' | 'cancelled' | 'completed' | 'pending';
  notes?: string;
  cancelReason?: string;
  cancelNote?: string;
  cancelledBy?: string; // 'patient' | 'doctor' | 'hospital' | 'admin'
  cancelledByName?: string;
  createdAt: string;
}
```

### Proposed Backend Appointment Model:
- `id` (UUID or prefixed CharField)
- `patient` (ForeignKey to `User` or `PatientProfile`, null=True for guest checkouts, on_delete=SET_NULL)
- `patient_name` (CharField, snapshot)
- `patient_phone` (CharField, snapshot)
- `patient_email` (EmailField, snapshot)
- `doctor` (ForeignKey to `Doctor`, on_delete=PROTECT)
- `hospital` (ForeignKey to `Hospital`, null=True, blank=True, on_delete=PROTECT)
- `clinic` (ForeignKey to `Clinic`, null=True, blank=True, on_delete=PROTECT)
- `specialty` (CharField, snapshot)
- `date` (DateField, indexed)
- `time_slot` (CharField, max_length=32, indexed)
- `status` (CharField, choices: `confirmed`, `cancelled`, `completed`, `pending`, default=`confirmed`, indexed)
- `notes` (TextField, blank=True)
- `cancel_reason` (TextField, blank=True)
- `cancelled_by_role` (CharField, choices: `patient`, `doctor`, `hospital`, `admin`, blank=True)
- `cancelled_by_user` (ForeignKey to `User`, null=True, blank=True, on_delete=SET_NULL)
- `created_at` (DateTimeField, auto_now_add=True)
- `updated_at` (DateTimeField, auto_now=True)

### Unique Concurrency Constraint:
- Database constraint: `UniqueConstraint(fields=['doctor', 'date', 'time_slot'], condition=Q(status__in=['confirmed', 'pending']), name='unique_active_doctor_slot')`
- Prevents double booking even under high concurrency.

---

## 10. Doctor Availability & Schedule Entity

Frontend usage in `DoctorSchedule.tsx` and `BookingPage.tsx`:
- `availableDays`: Array of weekdays (e.g. `['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday']`)
- `availableSlots`: Array of time intervals (e.g. `['09:00 - 09:30', '10:00 - 10:30', ...]`)
- Standard slot duration: 30 minutes (with 20-minute variants supported in slot generator).

### Proposed Backend Structure:
1. `DoctorSchedule`: OneToOne with `Doctor`:
   - `available_days`: ArrayField / JSONField containing active weekdays.
   - `available_slots`: JSONField containing active standard slots.
2. `SlotBooking` / Availability Endpoint:
   - Dynamic API: `GET /api/v1/doctors/{id}/availability/?date=YYYY-MM-DD`
   - Computes:
     - Is the doctor practicing on that weekday?
     - Configured slots for that doctor.
     - Subtracts slots with active appointments (`confirmed` or `pending`).
     - Returns available and booked slots directly.

---

## 11. Prescriptions & Consultation Records

### Frontend Audit:
- In `PatientDashboard.tsx` and `PatientBookings.tsx`:
  - When an appointment is `completed`, a button "Prescription" is rendered.
  - Clicking it displays an informative toast: *"Prescription is ready for pickup at clinic pharmacy."*
- In `Header.tsx`:
  - Notification type: `type: 'prescription'`, *"Digital Prescription Ready from Dr. Tariq Al-Mansoor ready for pharmacy pickup"*.
- In `DoctorDashboard.tsx`:
  - Doctors have a button to "Mark Completed" on consultations.

### Backend Recommendation:
- Create a lightweight `Prescription` entity linked to `Appointment`:
  - `appointment` (OneToOneField)
  - `doctor` (ForeignKey)
  - `patient` (ForeignKey)
  - `diagnosis` (CharField)
  - `medications` (JSONField or related table: name, dosage, frequency, duration)
  - `instructions` (TextField)
  - `issued_at` (DateTimeField)
- Strict access controls: Only the attending doctor and the owning patient can view it.

---

## 12. Reviews & Ratings Entity

Frontend usage in `PatientDashboard.tsx`, `PatientBookings.tsx`, and `DoctorDetails.tsx`:
- Modal allows rating from 1 to 5 stars (`★`) and writing an optional feedback `comment`.
- Updates doctor's `rating` average and `reviewCount`.
- Can only be submitted for completed appointments (`isCompleted && !isReviewed`).

### Proposed Backend Model (`DoctorReview`):
- `appointment` (OneToOneField to `Appointment` - ensures 1 review per visit)
- `doctor` (ForeignKey to `Doctor`, related_name='reviews')
- `patient` (ForeignKey to `User`)
- `rating` (PositiveSmallIntegerField, validator: 1 to 5)
- `comment` (TextField, blank=True)
- `created_at` (DateTimeField, auto_now_add=True)
- Signal/Method: Recalculates `doctor.rating` and `doctor.review_count` upon review creation.

---

## 13. Notifications Requirements

Frontend audit (`Header.tsx`):
- Shows unread notification count badge.
- Notification types: `'appointment' | 'prescription' | 'reminder'`.
- Static mock items include appointment confirmation, digital prescription ready, and upcoming visit reminders.

### Proposed Backend Model (`Notification`):
- `user` (ForeignKey to `User`, indexed)
- `title` (CharField)
- `description` (TextField)
- `notification_type` (CharField: `appointment`, `prescription`, `reminder`, `system`)
- `link` (CharField, blank=True)
- `is_read` (BooleanField, default=False)
- `created_at` (DateTimeField, auto_now_add=True)

---

## 14. Admin Functionality

Frontend audit (`src/pages/admin/*`):
1. **Analytics Overview (`AdminDashboard.tsx`):**
   - KPI counters: Total Registered Users, Active Doctors, Hospitals, Clinics, Total Appointments, Pending Onboarding Requests, Waitlist signups.
   - Status distribution charts (Confirmed vs Completed vs Cancelled).
   - Recent activity stream.
2. **Provider Onboarding Requests (`AdminRequests.tsx`):**
   - List requests from `JoinProviderPage.tsx`.
   - Update request status (`approved` or `rejected`).
3. **Doctor Verification & Roster Control (`AdminDoctors.tsx`):**
   - View all registered doctors with specialty and facility affiliation.
   - Toggle status: `Active` ↔ `Deactivated`.
4. **Hospital & Clinic Network Control (`AdminProviders.tsx`):**
   - View all facilities. Filter by type (Hospital vs Clinic) and status.
   - Toggle status: `Active` ↔ `Deactivated`.
5. **Global Booking Inspector (`AdminBookings.tsx`):**
   - Filter all platform appointments by status, search by patient or doctor name.
   - Execute administrative cancellations with cancellation notes.
6. **Analytical Reports (`AdminReports.tsx`):**
   - Aggregated metrics grouped by doctor, specialty, hospital.
   - Rolling periods: Daily, Weekly (7 days), Monthly, Total.
   - Export report as JSON.

---

## 15. Required API Endpoints Specification

Below is the comprehensive REST API endpoint map matching every frontend service and screen:

### A. Authentication (`/api/v1/auth/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `POST` | `/api/v1/auth/login/` | Email + password login, returns JWT tokens + user profile | `authService.login`, `LoginPage`, `LoginModal` |
| `POST` | `/api/v1/auth/register/` | Patient self-registration | `authService.register` |
| `POST` | `/api/v1/auth/token/refresh/` | Refresh JWT access token | Global API Client |
| `GET` | `/api/v1/auth/me/` | Fetch authenticated user profile & session | `authService.getCurrentSession`, `AuthContext` |
| `POST` | `/api/v1/auth/logout/` | Blacklist refresh token & clear server session | `authService.logout` |

### B. Public & Directory APIs (`/api/v1/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `GET` | `/api/v1/doctors/` | Search & filter doctors (specialty, location, emirate, keyword) | `doctorService.getAllDoctors`, `DoctorList`, `SearchPage`, `Home` |
| `GET` | `/api/v1/doctors/{id}/` | Get single doctor details, reviews, facility info | `doctorService.getDoctorById`, `DoctorDetails`, `BookingPage` |
| `GET` | `/api/v1/doctors/{id}/availability/` | Get available days and slots for specific date | `BookingPage`, `DoctorSchedule` |
| `GET` | `/api/v1/hospitals/` | List & search hospitals | `hospitalService.getAllHospitals`, `HospitalList`, `SearchPage`, `Home` |
| `GET` | `/api/v1/hospitals/{id}/` | Get hospital profile with doctors & departments | `hospitalService.getHospitalById`, `HospitalDetails` |
| `GET` | `/api/v1/clinics/` | List & search clinics | `clinicService.getAllClinics`, `ClinicList`, `SearchPage` |
| `GET` | `/api/v1/clinics/{id}/` | Get clinic profile with affiliated doctors | `clinicService.getClinicById`, `ClinicDetails` |
| `GET` | `/api/v1/specialties/` | List all medical specialties | `mockSpecialties`, `SpecialtiesPage`, Filters |
| `GET` | `/api/v1/conditions/` | List medical conditions A-Z with matching specialties | `mockConditions`, `ConditionsPage`, `Home` |
| `POST` | `/api/v1/provider-requests/` | Submit provider partnership application | `providerService.submitJoinRequest`, `JoinProviderPage` |
| `POST` | `/api/v1/waitlist/` | Subscribe to waitlist / newsletter | `waitlistService.joinWaitlist` |

### C. Booking & Appointments (`/api/v1/appointments/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `POST` | `/api/v1/appointments/` | Create a confirmed appointment (handles transactional slot validation) | `bookingService.createAppointment`, `BookingPage` |
| `GET` | `/api/v1/appointments/my/` | List appointments for authenticated patient | `bookingService.getAppointmentsByPatient`, `PatientBookings` |
| `GET` | `/api/v1/appointments/{id}/` | Get single appointment details | `bookingService.getAppointmentById` |
| `POST` | `/api/v1/appointments/{id}/cancel/` | Cancel appointment with reason | `bookingService.cancelAppointment`, `CancelModal` |
| `POST` | `/api/v1/appointments/{id}/complete/` | Mark appointment completed (Doctor only) | `bookingService.completeAppointment`, `DoctorDashboard` |
| `POST` | `/api/v1/appointments/{id}/review/` | Submit review & star rating for completed visit | `PatientDashboard`, `PatientBookings` |

### D. Patient Portal (`/api/v1/patient/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `GET` | `/api/v1/patient/profile/` | Get patient medical profile, allergies, insurance | `PatientProfile` |
| `PUT`/`PATCH` | `/api/v1/patient/profile/` | Update patient medical profile | `PatientProfile` |
| `GET` | `/api/v1/patient/dependents/` | List patient dependents | `PatientProfile` |
| `POST` | `/api/v1/patient/dependents/` | Add dependent | `PatientProfile` |
| `DELETE` | `/api/v1/patient/dependents/{id}/` | Remove dependent | `PatientProfile` |

### E. Doctor Portal (`/api/v1/doctor/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `GET` | `/api/v1/doctor/dashboard/` | Doctor KPI metrics (completion rate, weekly load, status counts) | `DoctorDashboard` |
| `GET` | `/api/v1/doctor/appointments/` | List appointments for logged-in doctor | `DoctorDashboard` |
| `GET` | `/api/v1/doctor/schedule/` | Get doctor's active practicing days & standard slots | `DoctorSchedule` |
| `PUT`/`PATCH` | `/api/v1/doctor/schedule/` | Update doctor's active practicing days & standard slots | `DoctorSchedule` |
| `GET` | `/api/v1/doctor/patients/` | Get directory of unique patients treated by doctor | `DoctorPatients` |

### F. Hospital / Clinic Portal (`/api/v1/hospital/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `GET` | `/api/v1/hospital/dashboard/` | Hospital KPI metrics, doctor utilization, appointment breakdown | `HospitalDashboard` |
| `GET` | `/api/v1/hospital/doctors/` | List doctors belonging ONLY to this facility | `HospitalDoctors` |
| `POST` | `/api/v1/hospital/doctors/` | Add a new doctor to this facility's roster | `HospitalDoctors` |
| `PATCH` | `/api/v1/hospital/doctors/{id}/status/` | Toggle doctor Active/Deactivated for this facility | `HospitalDoctors` |
| `GET` | `/api/v1/hospital/departments/` | List clinical departments for this facility | `HospitalDepartments` |
| `POST` | `/api/v1/hospital/departments/` | Add clinical department to this facility | `HospitalDepartments` |
| `GET` | `/api/v1/hospital/settings/` | Get facility configuration & operational contact | `HospitalSettings` |
| `PUT`/`PATCH` | `/api/v1/hospital/settings/` | Update facility operational settings | `HospitalSettings` |

### G. Admin Portal (`/api/v1/admin/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `GET` | `/api/v1/admin/dashboard/` | System-wide statistics and activity stream | `AdminDashboard` |
| `GET` | `/api/v1/admin/doctors/` | Platform-wide doctor list with status filter | `AdminDoctors` |
| `PATCH` | `/api/v1/admin/doctors/{id}/status/` | Activate or deactivate any doctor | `AdminDoctors` |
| `GET` | `/api/v1/admin/providers/` | Platform-wide hospital and clinic list | `AdminProviders` |
| `PATCH` | `/api/v1/admin/providers/{id}/status/` | Activate or deactivate any hospital or clinic | `AdminProviders` |
| `GET` | `/api/v1/admin/bookings/` | Global appointment inspection | `AdminBookings` |
| `GET` | `/api/v1/admin/requests/` | List provider onboarding requests | `AdminRequests` |
| `PATCH` | `/api/v1/admin/requests/{id}/status/` | Approve or reject onboarding request | `AdminRequests` |
| `GET` | `/api/v1/admin/reports/` | Analytical reports aggregated by specialty, doctor, facility | `AdminReports` |

### H. Notifications (`/api/v1/notifications/`)
| Method | Endpoint | Description | Frontend Consumer |
|---|---|---|---|
| `GET` | `/api/v1/notifications/` | List current user notifications | `Header` |
| `PATCH` | `/api/v1/notifications/{id}/read/` | Mark notification as read | `Header` |

---

## 16. Request & Response Formats Expected by Frontend

All responses must adhere to consistent, clean REST structures:

### Success Response Format:
```json
{
  "id": "apt_1727200000",
  "patientId": "usr_pat_1",
  "patientName": "Sarah Jenkins",
  "patientPhone": "+971 50 123 4567",
  "patientEmail": "patient@meetadr.demo",
  "doctorId": "doc_1",
  "doctorName": "Dr. Tariq Al-Mansoor",
  "doctorPhoto": "https://...",
  "hospitalId": "hosp_1",
  "providerName": "City Care Specialty Hospital",
  "facilityName": "City Care Specialty Hospital",
  "specialty": "Cardiology",
  "location": "Dubai Healthcare City",
  "date": "2026-09-26",
  "time": "10:00 AM",
  "timeSlot": "10:00 AM",
  "status": "confirmed",
  "notes": "Routine checkup",
  "createdAt": "2026-09-24T18:30:00Z"
}
```

### Error Response Format:
```json
{
  "error": "ConflictError",
  "message": "The selected time slot (10:00 AM) with Dr. Tariq Al-Mansoor has already been booked.",
  "code": "SLOT_ALREADY_BOOKED"
}
```

---

## 17. Entity Relationships Diagram

```
                        ┌───────────────────┐
                        │       User        │
                        └─────────┬─────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │ 1:1                    │ 1:1                    │ 1:1
         ▼                        ▼                        ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  PatientProfile  │     │      Doctor      │     │ Hospital/Clinic  │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                        │
         │ 1:M                    │ 1:M                    │ 1:M
         │ (dependents)           │ (available slots)      │ (doctors/depts)
         ▼                        ▼                        ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ PatientDependent │     │  DoctorSchedule  │     │FacilityDepartment│
└──────────────────┘     └────────┬─────────┘     └──────────────────┘
                                  │
                                  │ Belongs to Provider (Hospital OR Clinic)
                                  ├────────────────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   Appointment    │◀────── Unique Slot Booking
                         └────────┬─────────┘
                                  │
                   ┌──────────────┴──────────────┐
                   │ 1:1                         │ 1:1
                   ▼                             ▼
         ┌──────────────────┐          ┌──────────────────┐
         │   DoctorReview   │          │   Prescription   │
         └──────────────────┘          └──────────────────┘
```

---

## 18. Fields Required by Frontend

- **Doctor:** `id`, `name`, `nameAr`, `photo`, `specialty`, `specialInterest`, `experience`, `experienceAr`, `rating`, `reviewCount`, `location`, `hospitalId`, `clinicId`, `hospitalName`, `clinicName`, `about`, `aboutAr`, `education`, `availableDays`, `availableSlots`, `status`.
- **Hospital:** `id`, `name`, `nameAr`, `photo`, `location`, `address`, `addressAr`, `specialties`, `doctorCount`, `rating`, `emergencyAvailable`, `phone`, `operatingHours`, `operatingHoursAr`, `about`, `aboutAr`, `status`.
- **Clinic:** `id`, `name`, `photo`, `location`, `address`, `specialty`, `doctorCount`, `rating`, `phone`, `operatingHours`, `about`, `status`.
- **Appointment:** `id`, `patientId`, `patientName`, `patientPhone`, `patientEmail`, `doctorId`, `doctorName`, `doctorPhoto`, `hospitalId`, `clinicId`, `providerName`, `specialty`, `location`, `date`, `timeSlot`, `status`, `notes`, `cancelReason`, `cancelledBy`, `cancelledByName`, `createdAt`.
- **Patient Profile:** `name`, `email`, `phone`, `bloodGroup`, `emergencyContact`, `allergies`, `insuranceProvider`, `insuranceNumber`, `dependents`.
- **Provider Request:** `id`, `providerType`, `name`, `contactPerson`, `contactNumber`, `email`, `country`, `location`, `submittedAt`, `status`.

---

## 19. Redundant / Unnecessary Fields Detected in Frontend Mock Data

1. **`doctorIds` in Hospital and Clinic Mock Data:**
   - In `mockHospitals.ts` and `mockClinics.ts`, an array of strings `doctorIds: ['doc_1', 'doc_2']` is manually stored.
   - **Backend Rationale:** In a relational PostgreSQL database, storing a doctor ID array inside the hospital record leads to data anomalies and synchronization bugs. The relationship must be a single foreign key `Doctor.hospital` / `Doctor.clinic`. The list of doctors and `doctorCount` should be dynamically retrieved and serialized.
2. **Duplicate Phone & Mobile Fields:**
   - The frontend uses `patientPhone` and `patientMobile` interchangeably across appointments and patients.
   - **Backend Rationale:** Store a single normalized `phone_number` / `mobile` field and serialize both or use consistent field aliases in serializers.
3. **Duplicate Facility Name Fields:**
   - `providerName`, `facilityName`, and `hospitalName` are all used to represent the facility on an appointment.
   - **Backend Rationale:** Standardize foreign keys `hospital` and `clinic` and compute `facility_name` dynamically in the serializer.

---

## 20. Mock Data Sources Currently Used

- `INITIAL_USERS` in `mockUsers.ts`: 4 demo users (`patient@meetadr.demo`, `doctor@meetadr.demo`, `hospital@meetadr.demo`, `admin@meetadr.demo`) + 7 sample patients.
- `INITIAL_DOCTORS` in `mockDoctors.ts`: 12 comprehensive doctor profiles across Cardiology, Dermatology, Orthopedics, Pediatrics, Neurology, etc.
- `INITIAL_HOSPITALS` in `mockHospitals.ts`: 8 UAE hospitals (City Care, American Hospital, Emirates Hospital, Al-Noor, Gulf Specialty, Marina, Capital, Al-Zahra).
- `INITIAL_CLINICS` in `mockClinics.ts`: 6 UAE specialized clinics (Prime Dental, Dr. Joy Dental, CosmeSurge, Mediclinic Meadows, Aster Clinic, Kaya Skin).
- `INITIAL_APPOINTMENTS` in `mockAppointments.ts`: 24 rich appointments covering Confirmed, Completed, and Cancelled states with cancel reasons.
- `HEALTH_CONDITIONS` in `mockConditions.ts`: 100+ alphabetized health conditions with symptoms and specialty mappings.
- `SPECIALTIES` in `mockSpecialties.ts`: 18 specialty definitions and UAE emirate locations.

---

## 21. Features Clearly Implemented in Frontend

1. **Multi-role Navigation & Route Protection:** `ProtectedRoute` correctly restricts views based on authenticated role (`patient`, `doctor`, `hospital`, `admin`).
2. **Dynamic Schedule Generation:** `BookingPage` calculates valid 30-min slots based on doctor's practicing days and subtracts booked slots.
3. **Appointment Status Lifecycle:** Full support for `confirmed`, `completed`, and `cancelled` states with modal cancellation reasons.
4. **Interactive Review Flow:** Patient can submit 1-5 star reviews on completed visits; frontend tracks reviewed appointment IDs.
5. **Hospital Doctor Onboarding & Deactivation:** Hospital portal allows adding doctors and toggling active/inactive status.
6. **Admin Onboarding Applications Review:** Admin portal allows approving and rejecting hospital/clinic registration applications.
7. **Patient Dependents Management:** Add and delete family members under patient health profile.

---

## 22. Features That Appear Incomplete or Mock-Only

1. **Prescription Management:** The frontend only triggers an informative toast (*"Prescription is ready for pickup at clinic pharmacy"*). There is no form or UI for doctors to compose prescriptions or patients to view an Rx PDF.
2. **Patient Registration Page:** The frontend `LoginPage` links to `/login` or `/join` for registration, but there is no dedicated multi-field patient registration form component (the registration function exists in `AuthContext` and `authService.ts`).
3. **Password Reset / Forgot Password:** There are no UI screens or mock endpoints for password recovery.
4. **Payment Processing:** Mock appointments are immediately confirmed without payment transactions (matches project instructions: payment gateway is NOT part of current scope).

---

## 23. Features That Cannot Be Determined From Frontend Alone

1. **Email Confirmation / Verification:** Does a newly registered patient need to verify their email before booking?
2. **Provider Onboarding Approval Flow:** When an admin approves a `ProviderRequest` in `/admin/requests`, should the backend automatically create a `Hospital`/`Clinic` record and provision a login credential, or is that handled externally?
3. **Guest Checkout Linking:** When an unauthenticated user books an appointment and signs in during the flow, how should pre-existing guest bookings be associated?

---

## 24. Security Risks Implied by Current Frontend Architecture

1. **Client-Side ID Trust (Critical IDOR Risk):**
   - The frontend directly sets `patientId`, `doctorId`, `hospitalId`, `status`.
   - *Risk:* If a backend blindly accepts `POST /api/appointments/` with client-provided `patientId`, user A could book on behalf of user B or inspect user B's records.
   - *Fix:* The backend must extract `patient_id` exclusively from `request.user` and reject mismatched foreign keys.
2. **Cross-Provider Doctor Manipulation:**
   - In `HospitalDoctors.tsx`, a hospital creates a doctor with `hospitalId: 'hosp-1'`.
   - *Risk:* A malicious user could send `POST /api/hospital/doctors/` with another hospital's ID.
   - *Fix:* The backend must enforce that a hospital can only bind doctors to its own authenticated `hospital_id`.
3. **Race Condition in Slot Booking:**
   - If two patients select the same 10:00 AM slot concurrently, both could send requests simultaneously.
   - *Risk:* Double booking of doctors.
   - *Fix:* Use database transactions (`select_for_update`) and unique database constraints on `(doctor_id, date, time_slot)` for active appointments.
4. **Client-Side Role Escalation:**
   - `authService.register` accepts `role: UserRole = 'patient'`.
   - *Risk:* An attacker could send `role: "admin"` in a registration payload.
   - *Fix:* The registration endpoint must strictly ignore or reject any role other than `patient`.

---

## 25. Questions & Ambiguities Requiring User Decision

### BLOCKING QUESTIONS — PHASE 1

1. **Authentication Token Storage:**
   - Should JWT tokens be returned in the JSON response payload (stored in memory/localStorage by the client), or should the Refresh Token be stored in a secure, HTTP-only cookie to prevent XSS token theft?
   - *(Recommendation: Return Access Token in JSON response, and store Refresh Token in HTTP-only, SameSite Cookie for maximum security).*

2. **Provider Onboarding Application Approval:**
   - When an Admin approves a `ProviderRequest` (`/admin/requests`):
     - **Option A:** Simply mark the request status as `approved` and require the admin to manually register the facility later.
     - **Option B (Recommended):** Automatically instantiate the corresponding `Hospital` or `Clinic` record in `Deactivated` state and generate a temporary invitation credential for the facility administrator.

3. **Digital Prescriptions Scope:**
   - In the frontend, the prescription button only displays an alert indicating pickup readiness. Should the backend include a structured `Prescription` model linked to appointments (ready for Phase 9), or should appointment notes suffice for now?
   - *(Recommendation: Include a clean `Prescription` model with diagnosis and medication items so it's fully ready when the frontend builds the view modal).*

4. **Guest Patient Booking:**
   - Should unauthenticated users be allowed to complete a booking as a guest (providing name, email, phone without a password), or should the backend strictly require an authenticated patient user account?
   - *(Note: In `BookingPage.tsx`, the guest login modal intercepts unauthenticated bookings, but can we mandate account creation/login for all API appointments?)*

---

*End of Phase 0 Audit Document.*
