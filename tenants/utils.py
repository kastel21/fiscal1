"""
Multi-tenant: helpers for resolving device and scoping queries.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenants.models import Tenant


def get_device_for_tenant(tenant: "Tenant | None"):
    """
    Return the FiscalDevice for this tenant (first registered device with matching tenant).
    Returns None if tenant is None or no device found.
    """
    if tenant is None:
        return None
    from fiscal.models import FiscalDevice
    return FiscalDevice.objects.filter(tenant=tenant, is_registered=True).first()
