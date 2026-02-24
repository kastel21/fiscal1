"""Context processors for fiscal app."""

from fiscal.models import FiscalDevice
from fiscal.views import SESSION_DEVICE_KEY, get_device_for_request

from tenants.utils import get_device_for_tenant


def fdms_device(request):
    """Add FDMS device list and selected device. When request.tenant is set, only that tenant's devices are exposed; never global list."""
    if not request:
        return {}
    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        devices = list(FiscalDevice.objects.filter(tenant=tenant, is_registered=True).order_by("device_id"))
        device = get_device_for_tenant(tenant) if devices else None
    else:
        devices = list(FiscalDevice.objects.filter(is_registered=True).order_by("device_id"))
        device = get_device_for_request(request) if devices else None
    return {
        "fdms_devices": devices,
        "fdms_selected_device_id": device.device_id if device else None,
        "fdms_device_obj": device,
    }
