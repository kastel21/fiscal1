"""
Multi-tenant: resolve tenant and enforce access. Production-grade security.
- For normal web users: tenant comes from session only (X-Tenant-Slug ignored to prevent header injection).
- For superusers (and optional internal API): X-Tenant-Slug header is honored, then session.
- Anonymous users cannot access tenant routes (403).
- Access: user must be superuser or have tenant in user.tenants (via UserTenant); else 403.
- Only after validation do we set request.tenant and set_current_tenant().
- Allowed tenant IDs are cached on request.user._tenant_cache once per request for performance.
"""

import logging
import os

from django.conf import settings
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse

from tenants.context import clear_current_tenant, set_current_tenant
from tenants.models import Tenant
from tenants.utils import user_has_tenant_access

logger = logging.getLogger(__name__)

# Path prefixes that do not require a tenant (admin, login, select-tenant, health, static, etc.)
TENANT_EXEMPT_PREFIXES = (
    "/admin/",
    "/login/",
    "/logout/",
    "/create-company/",
    "/onboarding/",
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


def _honor_header_for_request(request):
    """True if we honor X-Tenant-Slug header (superuser or internal API client). Normal web users use session only."""
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_superuser", False):
        return True
    if getattr(settings, "TENANT_HEADER_FOR_INTERNAL_API", False):
        token = os.environ.get("INTERNAL_API_TOKEN") or getattr(settings, "INTERNAL_API_TOKEN", None)
        header_value = request.META.get("HTTP_X_INTERNAL_CLIENT") or request.headers.get("X-Internal-Client")
        if header_value and token and header_value != token:
            return False  # Invalid token; caller should return 403
        if header_value:
            return True
    return False


class TenantResolutionMiddleware:
    """
    Resolve tenant; enforce access. Header only for superusers/internal API; normal users use session only.
    Anonymous users get 403 on tenant routes. Only set request.tenant after access check.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        if tenant_exempt(request.path):
            return self.get_response(request)

        user = getattr(request, "user", None)
        # Cache allowed tenant IDs once per request for fast access checks
        if user and getattr(user, "is_authenticated", False) and not getattr(user, "is_superuser", False):
            if not hasattr(user, "_tenant_cache"):
                user._tenant_cache = set(
                    user.tenants.values_list("id", flat=True)
                )
        else:
            if user and hasattr(user, "_tenant_cache"):
                del user._tenant_cache

        slug = None
        header_value = request.META.get("HTTP_X_INTERNAL_CLIENT") or request.headers.get("X-Internal-Client")
        token = os.environ.get("INTERNAL_API_TOKEN") or getattr(settings, "INTERNAL_API_TOKEN", None)
        if getattr(settings, "TENANT_HEADER_FOR_INTERNAL_API", False) and header_value and token and header_value != token:
            return HttpResponseForbidden("Invalid internal client token.")
        honor_header = _honor_header_for_request(request)
        if honor_header:
            slug = request.META.get("HTTP_X_TENANT_SLUG") or request.headers.get("X-Tenant-Slug")
        if not slug and hasattr(request, "session"):
            slug = request.session.get("tenant_slug")

        if slug:
            slug = str(slug).strip()
            tenant = _get_valid_tenant(slug)
            if tenant:
                if not user or not getattr(user, "is_authenticated", False):
                    logger.warning("Tenant access denied: anonymous user for tenant=%s", tenant.slug)
                    return HttpResponseForbidden("Authentication required to access a tenant.")
                if not user_has_tenant_access(user, tenant):
                    logger.warning(
                        "Tenant access denied: user=%s tenant=%s",
                        getattr(user, "pk", None),
                        tenant.slug,
                    )
                    return HttpResponseForbidden(
                        "You do not have access to this tenant. Assign the tenant to your user in admin."
                    )
                request.tenant = tenant
                token = set_current_tenant(tenant)
                try:
                    return self.get_response(request)
                finally:
                    clear_current_tenant(token)
            else:
                logger.warning("Tenant not found or inactive: slug=%s", slug)

        # Auto-select single tenant: if user has exactly one allowed tenant, set session and retry same URL
        if user and getattr(user, "is_authenticated", False) and hasattr(request, "session"):
            if getattr(user, "is_superuser", False):
                tenants_qs = Tenant.objects.filter(is_active=True)
            else:
                tenants_qs = getattr(user, "tenants", None)
                if tenants_qs is not None:
                    tenants_qs = tenants_qs.filter(is_active=True)
                else:
                    tenants_qs = Tenant.objects.none()
            if tenants_qs.count() == 1:
                only_tenant = tenants_qs.first()
                if user_has_tenant_access(user, only_tenant):
                    request.session["tenant_slug"] = only_tenant.slug
                    return HttpResponseRedirect(request.get_full_path())
        if settings.DEBUG:
            return HttpResponseRedirect(reverse("select_tenant"))
        raise Http404("Tenant required: select a tenant or provide X-Tenant-Slug if authorized.")
