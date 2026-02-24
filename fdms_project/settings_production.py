"""
Production environment settings.
Use: DJANGO_SETTINGS_MODULE=fdms_project.settings_production

- Production DB (PostgreSQL recommended; SQLite supported)
- FDMS production API
- Separate device certs (never reuse staging certs)
- Log rotation and retention
- DEBUG=False, SECRET_KEY from env
"""

import os
from pathlib import Path

from .settings import *  # noqa: F401, F403

BASE_DIR = Path(__file__).resolve().parent.parent

# Production: never debug
DEBUG = False
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set in production")
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    raise ValueError("ALLOWED_HOSTS environment variable must be set in production")

# HTTPS / HSTS (production behind TLS)
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Database: prefer PostgreSQL if DATABASE_URL set
_db_url = os.environ.get("DATABASE_URL")
if _db_url and "postgres" in _db_url.lower():
    try:
        import dj_database_url
        DATABASES = {"default": dj_database_url.config(conn_max_age=600)}
    except ImportError:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": os.environ.get("DB_PATH", str(BASE_DIR / "db_production.sqlite3")),
            }
        }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DB_PATH", str(BASE_DIR / "db_production.sqlite3")),
        }
    }

# FDMS production API
FDMS_ENV = "PROD"
FDMS_BASE_URL = os.environ.get("FDMS_BASE_URL")
if not FDMS_BASE_URL:
    raise ValueError("FDMS_BASE_URL environment variable must be set in production")

# Production device (register separately; never use staging certs)
FDMS_DEVICE_ID = int(os.environ.get("FDMS_DEVICE_ID", "0") or "0")
FDMS_DEVICE_SERIAL_NO = os.environ.get("FDMS_DEVICE_SERIAL_NO", "")
FDMS_ACTIVATION_KEY = os.environ.get("FDMS_ACTIVATION_KEY", "")

# Log retention
LOGS_DIR = Path(os.environ.get("LOGS_DIR", str(BASE_DIR / "logs")))
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING["handlers"]["fdms_file"] = {
    "level": "INFO",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOGS_DIR / "fdms.log",
    "maxBytes": 10 * 1024 * 1024,  # 10 MB
    "backupCount": 30,  # 30 days retention
    "formatter": "simple",
}
LOGGING["handlers"]["fdms_json_file"] = {
    "level": "INFO",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOGS_DIR / "fdms_json.log",
    "maxBytes": 10 * 1024 * 1024,
    "backupCount": 30,
    "formatter": "json",
}
LOGGING["handlers"]["fdms_error_file"] = {
    "level": "ERROR",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOGS_DIR / "fdms_error.log",
    "maxBytes": 5 * 1024 * 1024,
    "backupCount": 90,  # 90 days for errors
    "formatter": "simple",
}
LOGGING["handlers"]["fdms_error_json_file"] = {
    "level": "ERROR",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOGS_DIR / "fdms_error_json.log",
    "maxBytes": 5 * 1024 * 1024,
    "backupCount": 90,
    "formatter": "json",
}

# Startup safety: refuse to run with DEBUG in production
if DEBUG:
    raise RuntimeError(
        "DEBUG must be False in production. "
        "Ensure DJANGO_SETTINGS_MODULE=fdms_project.settings_production and DEBUG is not overridden."
    )
