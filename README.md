# MeetAdr — Backend API Service

> Enterprise healthcare appointment booking and provider discovery platform for the UAE market.  
> Built with **Django 4.2 · Django REST Framework · SimpleJWT · PostgreSQL**

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 4.2 |
| API | Django REST Framework 3.14 |
| Auth | SimpleJWT (rotating refresh tokens, HttpOnly cookie) |
| API Docs | drf-spectacular (OpenAPI 3.0 — Swagger UI + ReDoc) |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL 15+ |
| Server (prod) | Gunicorn |

---

## Quick Start (Local Development)

```bash
# 1. Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements/local.txt

# 3. Copy environment file
cp .env.example .env

# 4. Run migrations
python manage.py migrate --settings=config.settings.local

# 5. (Optional) Seed sample data
python seed_local_db.py

# 6. Start server
python manage.py runserver --settings=config.settings.local
```

Server runs at **http://localhost:8000**

---

## API Documentation

Once the server is running:

| URL | Description |
|-----|-------------|
| `/api/docs/` | Swagger UI (interactive) |
| `/api/redoc/` | ReDoc documentation |
| `/api/schema/` | Download OpenAPI 3.0 schema (YAML) |
| `/api/v1/health/` | Health check endpoint |
| `/admin/` | Django Admin interface |

---

## Project Structure

```
backend/
├── apps/
│   ├── accounts/        # Auth, users, patient profiles & dependents
│   ├── facilities/      # Hospitals, clinics, departments
│   ├── doctors/         # Doctor profiles, schedules, portal
│   ├── appointments/    # Booking, reviews, cancellation
│   ├── prescriptions/   # Clinical prescriptions & medications
│   ├── onboarding/      # Provider partnership applications
│   ├── notifications/   # In-app notifications
│   └── audit/           # Immutable administrative audit log
├── config/
│   ├── settings/
│   │   ├── base.py      # Shared settings
│   │   ├── local.py     # Development (SQLite, DEBUG=True)
│   │   └── production.py# Production (PostgreSQL, HTTPS)
│   └── urls.py          # Root URL configuration
├── requirements/
│   ├── base.txt         # Core dependencies
│   ├── local.txt        # + pytest-django
│   └── production.txt   # + gunicorn, django-storages
├── tests/               # Comprehensive pytest test suite (15 files)
├── seed_local_db.py     # Local development data seeder
├── manage.py
└── .env.example         # Environment variable reference
```

---

## User Roles

| Role | Description |
|------|-------------|
| `patient` | Books appointments, manages profile & dependents |
| `doctor` | Manages schedule, consults patients, issues prescriptions |
| `hospital` | Facility administrator — manages doctors & appointments |
| `admin` | Platform superadministrator — global oversight |

---

## Running Tests

```bash
# Windows
.venv\Scripts\python.exe -m pytest --ds=config.settings.local -v

# macOS/Linux
python -m pytest --ds=config.settings.local -v

# Skip PostgreSQL concurrency tests (SQLite only)
python -m pytest --ds=config.settings.local -v --ignore=tests/test_concurrency_pg.py
```

---

## Settings & Environment

The project uses a **split settings** pattern. Always pass `--settings` to management commands:

```bash
# Local development
python manage.py <command> --settings=config.settings.local

# Or set the environment variable once
export DJANGO_SETTINGS_MODULE=config.settings.local
```

See `.env.example` for all available environment variables.

---

## Migrating to PostgreSQL

The project is **ready for PostgreSQL**. Set the following in your production environment:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DATABASE_URL=postgresql://user:password@host:5432/dbname
DJANGO_SECRET_KEY=<strong-secret>
AUTH_COOKIE_SECURE=true
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```

Then run:
```bash
pip install -r requirements/production.txt
python manage.py migrate --settings=config.settings.production
python manage.py collectstatic --settings=config.settings.production
gunicorn config.wsgi:application
```
