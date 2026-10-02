"""MeetAdr Local Development Settings."""
from .base import *

import os

DEBUG = True

ALLOWED_HOSTS = ['*']

# Database configuration: defaults to SQLite unless DATABASE_URL or DB_ENGINE is configured
if os.getenv('DATABASE_URL'):
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            default=os.getenv('DATABASE_URL'),
            conn_max_age=600,
        )
    }
elif os.getenv('DB_ENGINE') == 'django.db.backends.postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'postgres'),
            'USER': os.getenv('DB_USER', 'postgres'),
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

# Allow Browsable API in local development
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = (
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',
)

# Cookies for local dev
AUTH_COOKIE_SECURE = False
AUTH_COOKIE_SAMESITE = 'Lax'

# ── Email: print to console in local dev ─────────────────────────────────────
# Invitation emails will appear in the Django runserver terminal output.
# Copy the setup link from there to give to the hospital administrator.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Frontend URL for invitation links — must match the running Vite dev server port
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

import sys
if 'test' in sys.argv:
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]
