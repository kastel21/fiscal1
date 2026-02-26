"""
Multi-tenant: resolve tenant from X-Tenant-Slug header or session, attach request.tenant.
- Header takes precedence, then session (tenant_slug).
- In DEBUG=True only: if no tenant, redirect to /select-tenant/.
- In DEBUG=False: if no tenant, raise Http404. No fallback in production.
- /admin/, /select-tenant/, /static/, /media/, /health/ do not require tenant.
"""

import logging

from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse

from tenants.context import clear_current_tenant, set_current_tenant
from tenants.models import Tenant

logger = logging.getLogger(__name__)

# Path prefixes that do not require a tenant (admin, select-tenant, health, static, etc.)
TENANT_EXEMPT_PREFIXES = (
    "/admin/",
    "/select-tenant/",
    "/static/",
    "/media/",
    "/health/",
    "/api/health/",
)


def tenant_exempt(path: str) -> bool:
    """Return True if path should not require tenant resolution (request.tenant stays None)."""
    path = (path or "").strip().split("?")[0]
    if path in ("/", ""):
        return True
    for prefix in TENANT_EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _get_valid_tenant(slug: str):
    """Return Tenant for slug if active; else None. Always validates is_active."""
    if not (slug and str(slug).strip()):
        return None
    slug = str(slug).strip()
    try:
        return Tenant.objects.get(slug=slug, is_active=True)
    except (Tenant.DoesNotExist, ValueError, TypeError):
        return None


class TenantResolutionMiddleware:
    """
    Resolve tenant from (1) X-Tenant-Slug header, (2) session tenant_slug.
    Always validate with Tenant.objects.get(slug=slug, is_active=True).
    DEBUG=True only: if no tenant, redirect to /select-tenant/. DEBUG=False: Http404.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        if tenant_exempt(request.path):
            return self.get_response(request)

        # 1) Try header
        slug = request.META.get("HTTP_X_TENANT_SLUG") or request.headers.get("X-Tenant-Slug")
        # 2) If not found, try session
        if not slug and hasattr(request, "session"):
            slug = request.session.get("tenant_slug")

        if slug:
            slug = str(slug).strip()
            tenant = _get_valid_tenant(slug)
            if tenant:
                request.tenant = tenant
                token = set_current_tenant(tenant)
                try:
                    return self.get_response(request)
                finally:
                    clear_current_tenant(token)
            # Invalid slug: fall through to no-tenant handling
            logger.warning("Tenant not found or inactive: slug=%s", slug)

        # No valid tenant
        if settings.DEBUG:
            # Dev only: redirect to tenant selection (do NOT auto-redirect in production)
            return HttpResponseRedirect(reverse("select_tenant"))
        raise Http404("Tenant required: provide X-Tenant-Slug header or select a tenant.")
