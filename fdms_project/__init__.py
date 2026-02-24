# Load Celery app when Django starts so @shared_task decorators find it.
from fdms_project.celery import app as celery_app

__all__ = ("celery_app",)
