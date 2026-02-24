"""
Base FDMS service for ZIMRA Fiscal Data Management System integration.
Provides common headers and configuration for FDMS API calls.
"""

from django.conf import settings


class FDMSBaseService:
    """
    Base service class for FDMS API integration.
    Provides headers and configuration required by the FDMS API.
    """

    def headers(self) -> dict[str, str]:
        """
        Return HTTP headers required for FDMS API requests.

        Returns:
            dict: Headers including DeviceModelName, DeviceModelVersion,
                  and Content-Type.
        """
        return {
            "DeviceModelName": getattr(
                settings, "FDMS_DEVICE_MODEL_NAME", "YOUR_MODEL_NAME"
            ),
            "DeviceModelVersion": getattr(
                settings, "FDMS_DEVICE_MODEL_VERSION", "1.0"
            ),
            "Content-Type": "application/json",
        }
