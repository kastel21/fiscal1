"""Offline detection. Backend-driven."""

import logging

from fiscal.services.fdms_device_service import FDMSDeviceService

logger = logging.getLogger("fiscal")


class OfflineDetector:
    """Detect if FDMS is unreachable."""

    OFFLINE_INDICATORS = (
        "connection", "timeout", "refused", "unreachable",
        "tls", "handshake", "certificate", "network", "resolve",
    )

    @classmethod
    def is_offline(cls, device) -> tuple[bool, str | None]:
        """Returns (is_offline, error_message)."""
        try:
            FDMSDeviceService().get_status(device)
            return False, None
        except Exception as e:
            err_str = str(e).lower()
            if any(ind in err_str for ind in cls.OFFLINE_INDICATORS):
                logger.info("Offline detected: %s", e)
                return True, str(e)
            return False, str(e)
