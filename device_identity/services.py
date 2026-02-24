"""
Device identity service. UI calls only this.
Business logic: generate CSR, validate CN, call ZIMRA RegisterDevice, store certificate.
"""

from fiscal.models import FiscalDevice
from fiscal.services.device_registration import DeviceRegistrationService


def register_device(
    device_id: int,
    activation_key: str,
    device_serial_no: str,
    device_model_name: str = "",
    device_model_version: str = "",
) -> tuple[FiscalDevice | None, str | None]:
    """
    Register device with FDMS. Delegates to fiscal DeviceRegistrationService.
    Returns (device, None) on success, (None, error_message) on failure.
    """
    service = DeviceRegistrationService()
    return service.register_device(
        device_id=device_id,
        activation_key=activation_key.strip(),
        device_serial_no=device_serial_no.strip(),
        device_model_name=device_model_name.strip() or "Unknown",
        device_model_version=device_model_version.strip() or "v1",
    )
