"""
Multi-tenant: custom manager that optionally scopes queryset by current tenant.
Use when request.tenant is set (e.g. in views) or when tenant is set in context (e.g. in tasks).
"""

from django.db import models

from tenants.context import get_current_tenant


class TenantScopedManager(models.Manager):
    """
    Manager that filters by current tenant when one is set (context or request).
    Usage: add to model as objects = TenantScopedManager(); then Model.objects.all() returns only current tenant's rows when tenant is set.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is not None and hasattr(self.model, "tenant"):
            return qs.filter(tenant=tenant)
        return qs
