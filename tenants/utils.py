"""
Multi-tenant: helpers for resolving device, scoping queries, and tenant access.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenants.models import Tenant


def user_has_tenant_access(user, tenant):
    """
    Return True if the user is allowed to access the tenant.
    Superusers have access to all tenants. Otherwise user must be in user.tenants.
    Uses request.user._tenant_cache when set (by middleware) to avoid repeated DB hits.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if tenant is None:
        return False
    cache = getattr(user, "_tenant_cache", None)
    if cache is not None:
        return tenant.pk in cache
    return user.tenants.filter(pk=tenant.pk).exists()


def get_default_tenant():
    """
    Return the default tenant (first active tenant by created_at).
    Used so receipts/invoices without a device tenant are assigned to a tenant and show on lists.
    Returns None if no active tenant exists.
    """
    from tenants.models import Tenant
    return Tenant.objects.filter(is_active=True).order_by("created_at").first()


def get_device_for_tenant(tenant: "Tenant | None"):
    """
    Return the FiscalDevice for this tenant (first registered device with matching tenant).
    Returns None if tenant is None or no device found.
    """
    if tenant is None:
        return None
    from fiscal.models import FiscalDevice
    return FiscalDevice.objects.filter(tenant=tenant, is_registered=True).first()
