"""MeetAdr Production / Staging Settings."""
import os
import dj_database_url
from .base import *

DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() == 'true'

# Database Configuration:
# Automatically parses DATABASE_URL (Render Postgres, Supabase, AWS RDS),
# otherwise falls back to individual credentials, or SQLite for zero-config staging.
if os.getenv('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.getenv('DATABASE_URL'),
            conn_max_age=600,
        )
    }
elif os.getenv('DB_NAME') and os.getenv('DB_USER'):
    DATABASES = {
        'default': {
            'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql'),
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Production HTTPS Enforcement
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS Configuration
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = os.getenv('SECURE_HSTS_PRELOAD', 'False').lower() == 'true'

# Production Cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Frontend needs to read csrftoken for X-CSRFToken header
SESSION_COOKIE_SAMESITE = os.getenv('AUTH_COOKIE_SAMESITE', 'Lax')
CSRF_COOKIE_SAMESITE = os.getenv('AUTH_COOKIE_SAMESITE', 'Lax')
AUTH_COOKIE_SECURE = True
