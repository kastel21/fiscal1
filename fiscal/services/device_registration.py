"""
FDMS device registration service.
Handles VerifyTaxpayerInformation, RegisterDevice, and taxpayer profile persistence.
"""

import logging

import requests
from django.utils import timezone
from django.conf import settings

from fiscal.models import FiscalDevice
from fiscal.services.certificate_utils import generate_csr, generate_key_pair
from fiscal.services.key_storage import encrypt_private_key
from fiscal.services.fdms_base import FDMSBaseService
from fiscal.services.fdms_logger import log_fdms_call

logger = logging.getLogger("fiscal")


def _format_address(addr: dict | None) -> str:
    """Format AddressDto as a single line for display."""
    if not addr:
        return ""
    parts = []
    for k in ("street", "city", "province"):
        v = addr.get(k)
        if v:
            parts.append(str(v).strip())
    return ", ".join(parts) if parts else str(addr)[:200]


class DeviceRegistrationService(FDMSBaseService):
    """Service for registering fiscal devices with ZIMRA FDMS."""

    def verify_taxpayer_information(
        self,
        device_id: int,
        activation_key: str,
        device_serial_no: str,
    ) -> tuple[dict | None, str | None]:
        """
        Call VerifyTaxpayerInformation (Public API) before device registration.
        Returns taxpayer info so user can confirm correct taxpayer.

        Args:
            device_id: Sold or active device ID.
            activation_key: 8-symbol activation key (case insensitive).
            device_serial_no: Device serial number from manufacturer.

        Returns:
            tuple: (data dict with taxPayerName, taxPayerTIN, deviceBranchName,
                   deviceBranchAddress, vatNumber, operationID; or None) and
                   (error_message or None).
        """
        base_url = getattr(settings, "FDMS_BASE_URL", "").rstrip("/")
        endpoint = f"/Public/v1/{device_id}/VerifyTaxpayerInformation"
        url = f"{base_url}{endpoint}"

        headers = self.headers()
        payload = {
            "activationKey": activation_key.strip()[:8],
            "deviceSerialNo": device_serial_no.strip(),
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            log_fdms_call(
                endpoint=endpoint,
                method="POST",
                request_payload={"deviceId": device_id, "hasActivationKey": True},
                response=response,
            )

            if response.status_code != 200:
                try:
                    err_body = response.json()
                    detail = err_body.get("detail", err_body.get("title", response.text))
                except Exception:
                    detail = response.text or f"HTTP {response.status_code}"
                return None, detail

            data = response.json()
            addr = data.get("deviceBranchAddress") or {}
            formatted_addr = _format_address(addr)
            return {
                "taxPayerName": data.get("taxPayerName", ""),
                "taxPayerTIN": data.get("taxPayerTIN", ""),
                "deviceBranchName": data.get("deviceBranchName", ""),
                "deviceBranchAddress": formatted_addr or str(addr)[:200],
                "deviceBranchAddressRaw": addr if isinstance(addr, dict) else {},
                "vatNumber": data.get("vatNumber") or "",
                "operationID": data.get("operationID") or "",
            }, None

        except requests.RequestException as e:
            log_fdms_call(
                endpoint=endpoint,
                method="POST",
                request_payload={"deviceId": device_id},
                error=str(e),
            )
            return None, str(e)
        except Exception as e:
            logger.exception("VerifyTaxpayerInformation failed")
            log_fdms_call(endpoint=endpoint, method="POST", request_payload={}, error=str(e))
            return None, str(e)

    def register_device(
        self,
        device_id: int,
        activation_key: str,
        device_serial_no: str,
        device_model_name: str,
        device_model_version: str,
    ) -> tuple[FiscalDevice | None, str | None]:
        """
        Register device with FDMS: verify taxpayer, generate key/CSR, call RegisterDevice,
        store cert and taxpayer profile.

        Args:
            device_id: Sold or active device ID.
            activation_key: 8-symbol activation key (case insensitive).
            device_serial_no: Device serial number from manufacturer.

        Returns:
            tuple: (FiscalDevice on success, None) or (None, error_message).
        """
        verification, verify_err = self.verify_taxpayer_information(
            device_id=device_id,
            activation_key=activation_key,
            device_serial_no=device_serial_no,
        )
        if verify_err:
            return None, f"VerifyTaxpayerInformation failed: {verify_err}"
        if not verification:
            return None, "VerifyTaxpayerInformation returned no data"

        taxpayer_defaults = {
            "taxpayer_name": verification.get("taxPayerName") or "",
            "taxpayer_tin": verification.get("taxPayerTIN") or "",
            "vat_number": (verification.get("vatNumber") or "")[:9] or None,
            "branch_name": verification.get("deviceBranchName") or "",
            "branch_address": verification.get("deviceBranchAddressRaw"),
            "is_vat_registered": bool(verification.get("vatNumber")),
            "verification_operation_id": verification.get("operationID") or "",
            "verified_at": timezone.now(),
        }

        base_url = getattr(settings, "FDMS_BASE_URL", "").rstrip("/")
        endpoint = f"/Public/v1/{device_id}/RegisterDevice"
        url = f"{base_url}{endpoint}"

        headers = self.headers()
        headers.pop("Content-Type", None)
        headers["Content-Type"] = "application/json"
        logger.info("FDMS Headers: %s", headers)

        try:
            private_key_pem, _ = generate_key_pair()
            csr_pem = generate_csr(device_id, device_serial_no, private_key_pem)

            payload = {
                "activationKey": activation_key.strip()[:8],
                "certificateRequest": csr_pem,
            }

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            log_fdms_call(
                endpoint=endpoint,
                method="POST",
                request_payload={"deviceId": device_id, "hasCsr": True},
                response=response,
            )

            if response.status_code != 200:
                try:
                    err_body = response.json()
                    detail = err_body.get("detail", err_body.get("title", response.text))
                except Exception:
                    detail = response.text or f"HTTP {response.status_code}"
                return None, detail

            data = response.json()
            certificate_pem = data.get("certificate")
            if not certificate_pem:
                return None, "No certificate in response"

            key_to_store = (
                private_key_pem.decode() if isinstance(private_key_pem, bytes) else private_key_pem
            )
            key_to_store = encrypt_private_key(key_to_store)

            defaults = {
                "device_serial_no": device_serial_no,
                "device_model_name": device_model_name,
                "device_model_version": device_model_version,
                "certificate_pem": certificate_pem,
                "private_key_pem": key_to_store,
                "is_registered": True,
                "certificate_valid_till": None,
                **taxpayer_defaults,
            }
            device, created = FiscalDevice.objects.update_or_create(
                device_id=device_id,
                defaults=defaults,
            )
            logger.info("Device %s registered successfully", device_id)
            return device, None

        except requests.RequestException as e:
            log_fdms_call(
                endpoint=endpoint,
                method="POST",
                request_payload={"deviceId": device_id},
                error=str(e),
            )
            return None, str(e)
        except Exception as e:
            logger.exception("Device registration failed")
            log_fdms_call(
                endpoint=endpoint,
                method="POST",
                request_payload={},
                error=str(e),
            )
            return None, str(e)
