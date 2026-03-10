"""
Multi-tenant: admin mixin for tenant-scoped models (TenantAwareModel).
Uses all_objects when request.tenant is None so superadmin sees all records.
When request.tenant is set, filters by tenant.
"""

from django.contrib import admin


class TenantAdminMixin:
    """
    Mixin for ModelAdmin on TenantAwareModel (or models with tenant FK and all_objects).
    When request.tenant is None (e.g. admin): use all_objects so superadmin sees all tenants.
    When request.tenant is set: filter by that tenant.
    """

    def get_queryset(self, request):
        tenant = getattr(request, "tenant", None)
        if hasattr(self.model, "all_objects"):
            qs = self.model.all_objects.get_queryset()
        else:
            qs = super().get_queryset(request)
        if tenant is not None and hasattr(self.model, "tenant"):
            return qs.filter(tenant=tenant)
        return qs
