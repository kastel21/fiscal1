"""
Multi-tenant: resolve tenant from request and attach to request.tenant.
Uses X-Tenant-Slug header. Returns 404 if tenant not found or inactive.
"""

import logging

from django.http import Http404

from tenants.context import clear_current_tenant, set_current_tenant
from tenants.models import Tenant

logger = logging.getLogger(__name__)

# Path prefixes that do not require a tenant (health, static, admin, etc.)
TENANT_EXEMPT_PREFIXES = (
    "/admin/",
    "/static/",
    "/media/",
    "/health/",
    "/api/health/",
)


def tenant_exempt(path: str) -> bool:
    """Return True if path should not require tenant resolution (request.tenant stays None)."""
    path = (path or "").strip().split("?")[0]
    for prefix in TENANT_EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


class TenantResolutionMiddleware:
    """
    Resolve tenant from X-Tenant-Slug header and set request.tenant.
    Exempt paths (e.g. /admin/, /static/) get request.tenant = None.
    Non-exempt paths without valid header raise Http404.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        if tenant_exempt(request.path):
            return self.get_response(request)

        slug = request.META.get("HTTP_X_TENANT_SLUG") or request.headers.get("X-Tenant-Slug")
        if not slug:
            logger.warning("Missing X-Tenant-Slug header for path=%s", request.path)
            raise Http404("Tenant required: provide X-Tenant-Slug header.")

        slug = slug.strip()
        try:
            tenant = Tenant.objects.get(slug=slug, is_active=True)
        except Tenant.DoesNotExist:
            logger.warning("Tenant not found or inactive: slug=%s", slug)
            raise Http404("Tenant not found or inactive.")

        request.tenant = tenant
        token = set_current_tenant(tenant)
        try:
            response = self.get_response(request)
        finally:
            clear_current_tenant(token)
        return response
