"""Health check endpoints. No auth required for monitoring."""

from django.conf import settings
from django.http import JsonResponse


def fdms_health(request):
    """
    GET /health/fdms/
    Checks: certificate exists, certificate valid, getStatus reachable, last fiscal day state.
    Returns: OK, WARNING, CRITICAL
    """
    from fiscal.models import FiscalDevice
    from fiscal.services.device_api import DeviceApiService
    from django.utils import timezone

    status = "OK"
    checks = {}
    device = FiscalDevice.objects.filter(is_registered=True).first()

    if not device:
        return JsonResponse({
            "status": "WARNING",
            "checks": {"device": "No registered device"},
            "message": "No device registered",
        })

    checks["device"] = f"Device {device.device_id} registered"

    if not device.certificate_pem or not device.private_key_pem:
        status = "CRITICAL"
        checks["certificate"] = "Missing certificate or key"
    else:
        checks["certificate"] = "Present"

    if device.certificate_valid_till:
        now = timezone.now()
        if device.certificate_valid_till < now:
            status = "CRITICAL"
            checks["certificate_validity"] = "EXPIRED"
        elif (device.certificate_valid_till - now).days < 30:
            status = "WARNING" if status == "OK" else status
            checks["certificate_validity"] = f"Expires in {(device.certificate_valid_till - now).days} days"
        else:
            checks["certificate_validity"] = "Valid"
    else:
        checks["certificate_validity"] = "Unknown (getConfig not run)"

    checks["fiscal_day_status"] = device.fiscal_day_status or "unknown"

    try:
        service = DeviceApiService()
        data, err = service.get_status(device)
        if err:
            status = "WARNING" if status == "OK" else status
            checks["get_status"] = f"Error: {err[:100]}"
        else:
            checks["get_status"] = "Reachable"
    except Exception as e:
        status = "CRITICAL"
        checks["get_status"] = str(e)[:100]

    return JsonResponse({
        "status": status,
        "checks": checks,
    })
