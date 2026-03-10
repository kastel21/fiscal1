"""Context processors for fdms_project."""

from django.conf import settings


def branding(request):
    """Expose system branding to all templates."""
    return {
        "SYSTEM_NAME": getattr(settings, "SYSTEM_NAME", "FiscalFlow"),
        "SYSTEM_TAGLINE": getattr(settings, "SYSTEM_TAGLINE", "Seamless ZIMRA Fiscal Integration"),
    }
