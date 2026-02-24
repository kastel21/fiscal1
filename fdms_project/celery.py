"""Celery app for FDMS fiscal engine."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fdms_project.settings")

app = Celery("fdms_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
