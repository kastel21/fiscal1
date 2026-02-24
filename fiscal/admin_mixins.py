"""
Multi-tenant: admin mixin to scope queryset by request.tenant when set.
Superadmin (request.tenant is None in /admin/) sees all; when tenant is set (e.g. API) filter by it.
"""

from django.contrib import admin


class TenantAdminMixin:
    """
    Mixin for ModelAdmin: filter queryset by request.tenant when set.
    Models must have a 'tenant' ForeignKey. When request.tenant is None (e.g. admin without header), no filter.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, "tenant", None)
        if tenant is not None and hasattr(self.model, "tenant"):
            return qs.filter(tenant=tenant)
        return qs
