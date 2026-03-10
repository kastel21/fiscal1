"""
Multi-tenant: Stripe-style tenant guard.
TenantAwareManager automatically filters by current tenant (context/request).
When no tenant is set, returns empty queryset to prevent cross-tenant data leakage.
Use all_objects when global access is required (admin, migrations, background jobs).
"""

from django.db import models

from tenants.context import get_current_tenant


class TenantAwareManager(models.Manager):
    """
    Manager that filters by the current tenant from context (set by middleware or set_current_tenant).
    When no tenant is set, returns qs.none() so queries never leak data across tenants.
    Use Model.objects for tenant-scoped access; use Model.all_objects for unscoped access.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is None:
            return qs.none()
        if not hasattr(self.model, "tenant"):
            return qs.none()
        return qs.filter(tenant=tenant)


# Backward compatibility alias; prefer TenantAwareManager for new code.
TenantScopedManager = TenantAwareManager
