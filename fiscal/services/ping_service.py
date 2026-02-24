"""
FDMS Ping service: report device online to FDMS (section 4.13).
Multi-tenant: accepts Tenant; resolves device and calls DeviceApiService.ping(device).
"""

import logging
from typing import Any

from fiscal.services.device_api import DeviceApiService
from tenants.utils import get_device_for_tenant

logger = logging.getLogger("fiscal")


def send_ping(tenant, timeout_seconds: int = 30) -> tuple[dict | None, str | None]:
    """
    Send FDMS Ping for the given tenant. Resolves device from tenant and calls FDMS.

    Args:
        tenant: Tenant instance (must have device_id; device resolved via get_device_for_tenant).
        timeout_seconds: Request timeout (passed through to FDMS client).

    Returns:
        (response_data, None) on success; (None, error_message) on failure.
        response_data may contain operationID, reportingFrequency.
    """
    if tenant is None:
        return None, "Tenant is required"
    device = get_device_for_tenant(tenant)
    if device is None:
        logger.warning(
            "FDMS Ping skipped: no registered device for tenant",
            extra={"tenant_id": str(tenant.pk), "tenant_slug": tenant.slug, "device_id": tenant.device_id},
        )
        return None, "No registered device for tenant"
    service = DeviceApiService()
    data, err = service.ping(device)
    return data, err
