"""
FDMS Device Service - Mutual TLS communication with FDMS.
Implements GetStatus and device_request per Phase 4 spec.
Never uses verify=False. Never logs or exposes private keys.
"""

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

from fiscal.models import FiscalDay, FiscalDevice
from fiscal.services.fdms_base import FDMSBaseService
from fiscal.services.fdms_logger import log_fdms_call
from fiscal.services.http_client import fdms_request

logger = logging.getLogger("fiscal")


def get_decrypted_private_key(device: FiscalDevice) -> str:
    """
    Return decrypted private key PEM. Never log. Never expose to UI.
    If encrypted → decrypt. If not → return as is.
    """
    return device.get_private_key_pem_decrypted()


@contextmanager
def create_temp_cert_files(device: FiscalDevice):
    """
    Create secure temp cert/key files. Permissions 600.
    Yields (cert_path, key_path). Deletes files on exit.
    """
    if not device.certificate_pem or not device.private_key_pem:
        raise ValueError("Device has no certificate or private key")

    cert_pem = device.certificate_pem
    key_pem = get_decrypted_private_key(device)
    if isinstance(cert_pem, bytes):
        cert_pem = cert_pem.decode()
    if isinstance(key_pem, bytes):
        key_pem = key_pem.decode()

    tmpdir = Path(tempfile.gettempdir())
    cert_path = None
    key_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False, dir=tmpdir
        ) as cert_file:
            cert_file.write(cert_pem)
            cert_path = cert_file.name
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False, dir=tmpdir
        ) as key_file:
            key_file.write(key_pem)
            key_path = key_file.name
        try:
            os.chmod(cert_path, 0o600)
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        yield (cert_path, key_path)
    finally:
        if cert_path:
            Path(cert_path).unlink(missing_ok=True)
        if key_path:
            Path(key_path).unlink(missing_ok=True)


def update_device_status(device: FiscalDevice, status_json: dict) -> None:
    """
    Persist GetStatus response to database.
    - Update last_fiscal_day_no, last_receipt_global_no, fiscal_day_status
    - If FiscalDayClosed: update or create FiscalDay, save fiscalDayClosed
    - If FiscalDayCloseFailed: mark last FiscalDay as failed
    """
    from django.utils.dateparse import parse_datetime

    device.last_fiscal_day_no = status_json.get("lastFiscalDayNo")
    device.last_receipt_global_no = status_json.get("lastReceiptGlobalNo")
    device.fiscal_day_status = status_json.get("fiscalDayStatus")

    status = device.fiscal_day_status
    fiscal_day_no = device.last_fiscal_day_no
    fiscal_day_closed = status_json.get("fiscalDayClosed")
    closing_error_code = status_json.get("fiscalDayClosingErrorCode")

    if status == "FiscalDayClosed" and fiscal_day_no is not None:
        from django.utils import timezone
        closed_at = parse_datetime(fiscal_day_closed) if fiscal_day_closed else timezone.now()
        FiscalDay.objects.filter(
            device=device,
            fiscal_day_no=fiscal_day_no,
        ).update(status="FiscalDayClosed", closed_at=closed_at, closing_error_code=None)
    elif status == "FiscalDayCloseFailed" and fiscal_day_no is not None:
        FiscalDay.objects.filter(
            device=device,
            fiscal_day_no=fiscal_day_no,
            status="FiscalDayOpened",
        ).update(status="FiscalDayCloseFailed", closing_error_code=closing_error_code)

    device.save(update_fields=[
        "last_fiscal_day_no", "last_receipt_global_no", "fiscal_day_status"
    ])


class FDMSDeviceService(FDMSBaseService):
    """
    FDMS Device API service with mutual TLS.
    Implements device_request and get_status.
    """

    def device_request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        body: str | None = None,
        device: FiscalDevice | None = None,
    ):
        """
        Perform FDMS device request with mutual TLS.
        If body is provided, send it as request body; otherwise use json=payload.
        Uses cert=(cert_path, key_path), verify=True. Never verify=False.
        """
        base_url = getattr(settings, "FDMS_BASE_URL", "").rstrip("/")
        url = f"{base_url}{path}"

        headers = {
            "DeviceModelName": getattr(
                settings, "FDMS_DEVICE_MODEL_NAME", "YOUR_MODEL_NAME"
            ),
            "DeviceModelVersion": getattr(
                settings, "FDMS_DEVICE_MODEL_VERSION", "1.0"
            ),
            "Content-Type": "application/json",
        }

        if not device:
            raise ValueError("device required for mTLS")

        logger.info("FDMS Headers: %s", headers)
        with create_temp_cert_files(device) as (cert_path, key_path):
            if body is not None:
                response = fdms_request(
                    method, url, data=body, headers=headers,
                    cert=(cert_path, key_path), timeout=30,
                )
            else:
                response = fdms_request(
                    method, url, json=payload, headers=headers,
                    cert=(cert_path, key_path), timeout=30,
                )
            log_fdms_call(
                endpoint=path,
                method=method.upper(),
                request_payload=payload or {},
                response=response,
                tenant=getattr(device, "tenant", None),
            )
        return response

    def get_status(self, device: FiscalDevice) -> dict:
        """
        GET /Device/v1/{deviceID}/GetStatus
        Returns parsed JSON. Raises on error. Updates device via update_device_status.
        """
        if not device.is_registered:
            raise ValueError("Device is not registered")

        path = f"/Device/v1/{device.device_id}/GetStatus"
        response = self.device_request("GET", path, device=device)

        if response.status_code != 200:
            try:
                err_body = response.json()
                detail = err_body.get("detail", err_body.get("title", response.text))
            except Exception:
                detail = response.text or f"HTTP {response.status_code}"
            logger.error("GetStatus failed for device %s: %s", device.device_id, detail)
            raise FDMSDeviceError(detail, status_code=response.status_code)

        data = response.json()
        update_device_status(device, data)
        return data

    def ping(self, device: FiscalDevice) -> dict:
        """
        POST /Device/v1/{deviceID}/Ping
        Report device is online to FDMS. Returns operationID and reportingFrequency (minutes).
        """
        if not device.is_registered:
            raise ValueError("Device is not registered")

        path = f"/Device/v1/{device.device_id}/Ping"
        logger.info("Ping request: POST %s", path)
        response = self.device_request("POST", path, device=device)

        if response.status_code != 200:
            try:
                err_body = response.json()
                detail = err_body.get("detail", err_body.get("title", response.text))
            except Exception:
                detail = response.text or f"HTTP {response.status_code}"
            logger.error("Ping failed for device %s: %s", device.device_id, detail)
            raise FDMSDeviceError(detail, status_code=response.status_code)

        data = response.json()
        logger.info("Ping response:\n%s", json.dumps(data, indent=2, default=str))
        return data


class FDMSDeviceError(Exception):
    """Controlled exception for FDMS device API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
