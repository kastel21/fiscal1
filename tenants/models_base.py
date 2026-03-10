"""
Multi-tenant: abstract base for tenant-scoped models (Stripe-style guard).
Inherit from TenantAwareModel so Model.objects automatically filters by current tenant.
Use Model.all_objects when you need to bypass the guard (admin, migrations, tasks with explicit tenant).
Subclasses must define their own tenant ForeignKey; this mixin only adds the managers.
"""

from django.db import models

from tenants.managers import TenantAwareManager


class TenantAwareModel(models.Model):
    """
    Abstract base for models that belong to a tenant.
    - objects: TenantAwareManager (filters by get_current_tenant(); empty when no tenant).
    - all_objects: unscoped Manager for admin/migrations/tasks.
    Subclasses must define a 'tenant' ForeignKey to tenants.Tenant for the manager to filter on.
    """

    objects = TenantAwareManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
