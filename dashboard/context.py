"""Dashboard context: phase-gated navigation state computed from backend."""

from fiscal.models import FiscalDevice, Receipt


def get_offline_status() -> dict:
    """Offline mode status: is_offline, queue_size, last_submission_at."""
    device = FiscalDevice.objects.filter(is_registered=True).first()
    if not device:
        return {"is_offline": False, "queue_size": 0, "last_submission_at": None, "device": None}

    try:
        from offline.services.offline_detector import OfflineDetector
        from offline.services.queue_manager import QueueManager
        from offline.models import OfflineReceiptQueue

        is_offline, _ = OfflineDetector.is_offline(device)
        queue_size = QueueManager.queue_size(device=device)
        last_sub = (
            OfflineReceiptQueue.objects.filter(receipt__device=device, state="SUBMITTED")
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        return {
            "is_offline": is_offline,
            "queue_size": queue_size,
            "last_submission_at": last_sub,
            "device": device,
        }
    except Exception:
        return {"is_offline": False, "queue_size": 0, "last_submission_at": None, "device": device}


def get_navigation_state() -> dict:
    """
    Compute phase-gated sidebar state from backend device state.
    Returns dict with menu item enabled flags and device info.
    """
    device = FiscalDevice.objects.filter(is_registered=True).first()
    has_device = device is not None and device.is_registered

    fiscal_day_open = False
    if device and device.fiscal_day_status:
        fiscal_day_open = device.fiscal_day_status == "FiscalDayOpened"

    has_activity = (
        Receipt.objects.exists() or
        FiscalDevice.objects.filter(is_registered=True).exists()
    )

    return {
        "has_device": has_device,
        "fiscal_day_open": fiscal_day_open,
        "has_activity": has_activity,
        "device": device,
        "device_id": device.device_id if device else None,
        "certificate_status": "Stored" if (device and device.certificate_pem) else "None",
    }
