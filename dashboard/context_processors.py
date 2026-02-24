"""Context processors for dashboard. Inject phase-gated nav state into all templates."""

from django.conf import settings

from .context import get_navigation_state, get_offline_status


def dashboard_nav(request):
    """Add navigation state, offline status, and FDMS env to template context."""
    try:
        nav = get_navigation_state()
    except Exception:
        nav = {"has_device": False, "fiscal_day_open": False, "has_activity": False, "device": None, "device_id": None, "certificate_status": "—"}
    try:
        offline_status = get_offline_status()
    except Exception:
        offline_status = {"is_offline": False, "queue_size": 0, "last_submission_at": None}
    fdms_env = getattr(settings, "FDMS_ENV", "TEST")
    return {
        "nav": nav,
        "offline_status": offline_status,
        "fdms_env": fdms_env,
    }
