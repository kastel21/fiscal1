"""
Staging environment settings.
Use: DJANGO_SETTINGS_MODULE=fdms_project.settings_staging

- Separate DB (staging db.sqlite3)
- FDMS test/sandbox API
- Separate device certs (register staging device only)
- Log rotation enabled
"""

import os
from pathlib import Path

from .settings import *  # noqa: F401, F403

BASE_DIR = Path(__file__).resolve().parent.parent

# Staging: non-debug, restricted
DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,staging.example.com").split(",")

# Separate DB per environment
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db_staging.sqlite3",
    }
}

# FDMS: staging/test API only
FDMS_ENV = "STAGING"
FDMS_BASE_URL = os.environ.get("FDMS_BASE_URL", "https://fdmsapitest.zimra.co.zw")

# Staging device (register separately; never use prod certs)
FDMS_DEVICE_ID = int(os.environ.get("FDMS_DEVICE_ID", "0") or "0")
FDMS_DEVICE_SERIAL_NO = os.environ.get("FDMS_DEVICE_SERIAL_NO", "")
FDMS_ACTIVATION_KEY = os.environ.get("FDMS_ACTIVATION_KEY", "")

# Log retention: RotatingFileHandler (see base LOGGING overrides below)
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING["handlers"]["fdms_file"] = {
    "level": "INFO",
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOGS_DIR / "fdms.log",
    "maxBytes": 10 * 1024 * 1024,  # 10 MB
    "backupCount": 30,
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
    "backupCount": 90,
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
