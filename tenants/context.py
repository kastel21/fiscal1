"""
Multi-tenant: current tenant context for use in services/tasks where request is not available.
Uses contextvars so async-safe. Set in middleware; optionally set in tasks from device/tenant.
"""

from __future__ import annotations

from contextvars import ContextVar

from tenants.models import Tenant

# Current tenant for this request/task. Set by middleware or at task start.
current_tenant: ContextVar[Tenant | None] = ContextVar("tenant", default=None)


def get_current_tenant():
    """Return the current tenant from context, or None."""
    return current_tenant.get(None)


def set_current_tenant(tenant):
    """Set the current tenant in context (e.g. in Celery task). Returns token for reset."""
    return current_tenant.set(tenant)


def clear_current_tenant(token=None):
    """Reset tenant context. Pass token from set_current_tenant to reset to previous value."""
    if token is not None:
        current_tenant.reset(token)
    else:
        try:
            current_tenant.set(None)
        except LookupError:
            pass
