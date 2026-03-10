import logging

from django.apps import AppConfig


logger = logging.getLogger("fiscal")


class FiscalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fiscal"

    def ready(self):
        import fiscal.signals  # noqa: F401

        from django.conf import settings
        fdms_env = getattr(settings, "FDMS_ENV", "TEST")
        if fdms_env == "TEST":
            logger.warning("WARNING: FDMS running in TEST environment")
