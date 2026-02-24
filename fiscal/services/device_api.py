"""
FDMS Device API service.
Implements authenticated (mTLS) Device endpoints.
"""

import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings

from fiscal.models import FiscalDay, FiscalDevice, Receipt
from fiscal.services.close_day_counter_builder import build_close_day_counters
from fiscal.services.fdms_base import FDMSBaseService
from fiscal.services.fdms_logger import log_fdms_call
from fiscal.services.fiscal_signature import build_fiscal_day_canonical_string, sign_fiscal_day_report
from fiscal.services.http_client import fdms_request
from fiscal.services.mtls_client import cert_files_for_device
from fiscal.services.receipt_service import _fdms_json_dumps

logger = logging.getLogger("fiscal")

ALLOWED_CLOSE_STATUSES = ("FiscalDayOpened", "FiscalDayCloseFailed")


class DeviceApiService(FDMSBaseService):
    """Service for FDMS Device API calls (requires mutual TLS)."""

    def get_status(self, device: FiscalDevice) -> tuple[dict | None, str | None]:
        """
        Call GET /Device/v1/{deviceID}/GetStatus. Delegates to FDMSDeviceService.
        Returns (response_data, None) or (None, error_message).
        """
        from fiscal.services.fdms_device_service import FDMSDeviceService, FDMSDeviceError
        try:
            service = FDMSDeviceService()
            data = service.get_status(device)
            return data, None
        except FDMSDeviceError as e:
            return None, str(e)
        except ValueError as e:
            return None, str(e)

    def ping(self, device: FiscalDevice) -> tuple[dict | None, str | None]:
        """
        Call GET /Device/v1/{deviceID}/Ping to report device is online to FDMS.
        Returns (response_data with operationID, reportingFrequency, None) or (None, error_message).
        """
        from fiscal.services.fdms_device_service import FDMSDeviceService, FDMSDeviceError
        try:
            service = FDMSDeviceService()
            data = service.ping(device)
            return data, None
        except FDMSDeviceError as e:
            return None, str(e)
        except ValueError as e:
            return None, str(e)

    def get_config(self, device: FiscalDevice) -> tuple[dict | None, str | None]:
        """
        Call GET /Device/v1/{deviceID}/GetConfig.
        Updates certificate_valid_till from response.
        """
        base_url = getattr(settings, "FDMS_BASE_URL", "").rstrip("/")
        device_id = device.device_id
        endpoint = f"/Device/v1/{device_id}/GetConfig"
        url = f"{base_url}{endpoint}"

        headers = self.headers()

        logger.info("FDMS Headers: %s", headers)
        try:
            with cert_files_for_device(device) as (cert_path, key_path):
                response = fdms_request(
                    "GET", url, headers=headers,
                    cert=(cert_path, key_path), timeout=30,
                )
        except ValueError as e:
            log_fdms_call(endpoint=endpoint, method="GET", request_payload={"deviceId": device_id}, error=str(e), tenant=getattr(device, "tenant", None))
            return None, str(e)

        log_fdms_call(
            endpoint=endpoint, method="GET",
            request_payload={"deviceId": device_id},
            response=response,
            tenant=getattr(device, "tenant", None),
        )

        if response.status_code != 200:
            try:
                err_body = response.json()
                detail = err_body.get("detail", err_body.get("title", response.text))
            except Exception:
                detail = response.text or f"HTTP {response.status_code}"
            return None, detail

        data = response.json()
        from django.utils.dateparse import parse_datetime
        valid_till = data.get("certificateValidTill")
        if valid_till:
            parsed = parse_datetime(valid_till)
            if parsed:
                device.certificate_valid_till = parsed
                device.save(update_fields=["certificate_valid_till"])
        from fiscal.services.config_service import persist_configs
        persist_configs(device_id, data)
        logger.info("GetConfig OK for device %s", device_id)
        return data, None

    def issue_certificate(self, device: FiscalDevice) -> tuple[FiscalDevice | None, str | None]:
        """
        Call POST /Device/v1/{deviceID}/IssueCertificate to renew certificate.
        Generates new CSR, keeps private key. Updates certificate_pem on success.
        """
        if not device.device_serial_no:
            return None, "Device serial number required for certificate renewal"
        from fiscal.services.certificate_utils import generate_csr
        csr_pem = generate_csr(
            device.device_id,
            device.device_serial_no,
            device.get_private_key_pem_decrypted(),
        )
        base_url = getattr(settings, "FDMS_BASE_URL", "").rstrip("/")
        device_id = device.device_id
        endpoint = f"/Device/v1/{device_id}/IssueCertificate"
        url = f"{base_url}{endpoint}"
        headers = self.headers()
        payload = {"certificateRequest": csr_pem}
        logger.info("FDMS Headers: %s", headers)
        try:
            with cert_files_for_device(device) as (cert_path, key_path):
                response = fdms_request(
                    "POST", url, json=payload, headers=headers,
                    cert=(cert_path, key_path), timeout=30,
                )
        except ValueError as e:
            log_fdms_call(endpoint=endpoint, method="POST", request_payload={"hasCsr": True}, error=str(e), tenant=getattr(device, "tenant", None))
            return None, str(e)
        log_fdms_call(endpoint=endpoint, method="POST", request_payload={"hasCsr": True}, response=response, tenant=getattr(device, "tenant", None))
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
        device.certificate_pem = certificate_pem
        device.certificate_valid_till = None
        device.save(update_fields=["certificate_pem", "certificate_valid_till"])
        logger.info("IssueCertificate OK for device %s", device_id)
        return device, None

    def open_day(self, device: FiscalDevice) -> tuple[FiscalDay | None, str | None]:
        """
        Open a new fiscal day. Calls getStatus first; only proceeds if FiscalDayClosed.

        Computes fiscalDayNo: 1 if first day, else lastFiscalDayNo + 1.
        Creates local FiscalDay record on success.

        Args:
            device: FiscalDevice with certificate and private key.

        Returns:
            tuple: (FiscalDay on success, None) or (None, error_message).
        """
        status_data, err = self.get_status(device)
        if err:
            return None, f"GetStatus failed: {err}"
        if status_data.get("fiscalDayStatus") != "FiscalDayClosed":
            status = status_data.get("fiscalDayStatus", "unknown")
            return None, f"Cannot open day: status must be FiscalDayClosed (current: {status})"

        last_no = device.last_fiscal_day_no
        fiscal_day_no = 1 if last_no is None else last_no + 1
        fiscal_day_opened = datetime.now().isoformat(sep="T", timespec="seconds")

        base_url = getattr(settings, "FDMS_BASE_URL", "").rstrip("/")
        device_id = device.device_id
        endpoint = f"/Device/v1/{device_id}/OpenDay"
        url = f"{base_url}{endpoint}"

        headers = self.headers()

        payload = {
            "fiscalDayNo": fiscal_day_no,
            "fiscalDayOpened": fiscal_day_opened,
        }

        logger.info("FDMS Headers: %s", headers)
        try:
            with cert_files_for_device(device) as (cert_path, key_path):
                response = fdms_request(
                    "POST",
                    url,
                    json=payload,
                    headers=headers,
                    cert=(cert_path, key_path),
                    timeout=30,
                )
        except ValueError as e:
            log_fdms_call(
                endpoint=endpoint,
                method="POST",
                request_payload=payload,
                error=str(e),
                tenant=getattr(device, "tenant", None),
            )
            return None, str(e)

        log_fdms_call(
            endpoint=endpoint,
            method="POST",
            request_payload=payload,
            response=response,
            tenant=getattr(device, "tenant", None),
        )

        if response.status_code != 200:
            try:
                err_body = response.json()
                detail = err_body.get("detail", err_body.get("title", response.text))
            except Exception:
                detail = response.text or f"HTTP {response.status_code}"
            return None, detail

        data = response.json()
        returned_fiscal_day_no = data.get("fiscalDayNo", fiscal_day_no)

        opened_at = datetime.now()
        fiscal_day = FiscalDay.objects.create(
            device=device,
            fiscal_day_no=returned_fiscal_day_no,
            status="FiscalDayOpened",
            opened_at=opened_at,
            closed_at=None,
        )
        device.last_fiscal_day_no = returned_fiscal_day_no
        device.fiscal_day_status = "FiscalDayOpened"
        device.save(update_fields=["last_fiscal_day_no", "fiscal_day_status"])
        logger.info("OpenDay OK for device %s: fiscal day #%s", device_id, returned_fiscal_day_no)
        return fiscal_day, None

    def _build_close_day_payload(
        self,
        device: FiscalDevice,
        fiscal_day_no: int,
        last_receipt_no: int | None,
    ) -> tuple[dict, str] | tuple[None, str]:
        """
        Build CloseDay payload from receipts for the fiscal day.
        Uses receipts as source of truth; never fabricates counters.
        """
        receipts = Receipt.objects.filter(device=device, fiscal_day_no=fiscal_day_no)
        fiscal_day_obj = FiscalDay.objects.filter(device=device, fiscal_day_no=fiscal_day_no).first()
        fiscal_day_date = fiscal_day_obj.opened_at.date() if fiscal_day_obj and fiscal_day_obj.opened_at else date.today()

        if not receipts.exists():
            receipt_counter = 0
            counters: list[dict] = []
            canonical = build_fiscal_day_canonical_string(
                device_id=device.device_id,
                fiscal_day_no=fiscal_day_no,
                fiscal_day_date=fiscal_day_date,
                fiscal_day_counters=counters,
            )
            sig = sign_fiscal_day_report(
                device_id=device.device_id,
                fiscal_day_no=fiscal_day_no,
                fiscal_day_date=fiscal_day_date,
                fiscal_day_counters=counters,
                private_key_pem=device.get_private_key_pem_decrypted(),
                certificate_pem=device.certificate_pem,
            )
            payload = {
                "deviceID": device.device_id,
                "fiscalDayNo": fiscal_day_no,
                "receiptCounter": receipt_counter,
                "fiscalDayCounters": counters,
                "fiscalDayDeviceSignature": sig,
            }
            logger.debug(
                "CloseDay (no receipts): receipt_counter=%s counters=%s canonical=%s payload=%s",
                receipt_counter, counters, canonical, json.dumps(payload, indent=2, default=str),
            )
            logger.info("CloseDay canonical string: %s", canonical)
            logger.info("CloseDay signature hash: %s", sig.get("hash"))
            return payload, ""

        counters = build_close_day_counters(device, fiscal_day_no)
        fiscalised_receipts = Receipt.objects.filter(
            device=device, fiscal_day_no=fiscal_day_no
        ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0)
        receipt_counter = fiscalised_receipts.count()
        if receipt_counter > 0 and not counters:
            return None, "receiptCounter > 0 but fiscalDayCounters empty; aborting before FDMS"

        canonical = build_fiscal_day_canonical_string(
            device_id=device.device_id,
            fiscal_day_no=fiscal_day_no,
            fiscal_day_date=fiscal_day_date,
            fiscal_day_counters=counters,
        )
        receipt_global_nos = list(receipts.values_list("receipt_global_no", flat=True))
        logger.debug(
            "CloseDay: receipt_counter=%s counters=%s canonical=%s device.last_receipt_global_no=%s receipt_global_nos=%s",
            receipt_counter, counters, canonical, device.last_receipt_global_no, receipt_global_nos,
        )
        sig = sign_fiscal_day_report(
            device_id=device.device_id,
            fiscal_day_no=fiscal_day_no,
            fiscal_day_date=fiscal_day_date,
            fiscal_day_counters=counters,
            private_key_pem=device.get_private_key_pem_decrypted(),
            certificate_pem=device.certificate_pem,
        )

        payload = {
            "deviceID": device.device_id,
            "fiscalDayNo": fiscal_day_no,
            "receiptCounter": receipt_counter,
            "fiscalDayCounters": counters,
            "fiscalDayDeviceSignature": sig,
        }
        logger.debug("CloseDay payload: %s", json.dumps(payload, indent=2, default=str))
        logger.info("CloseDay canonical string: %s", canonical)
        logger.info("CloseDay signature hash: %s", sig.get("hash"))
        return payload, ""

    def close_day(
        self,
        device: FiscalDevice,
        sale_by_tax: list[dict] | None = None,
        refund_by_tax: list[dict] | None = None,
    ) -> tuple[dict | None, str | None]:
        """
        Close fiscal day. Calls getStatus first; only proceeds if FiscalDayOpened or FiscalDayCloseFailed.

        Builds fiscalDayCounters (SaleByTax, CreditNoteByTax), signs with device key, calls CloseDay.
        Does NOT poll - returns immediately after CloseDay accepts. Caller should poll getStatus.

        Args:
            device: FiscalDevice with certificate and private key.
            sale_by_tax: Optional list of sale counter dicts.
            refund_by_tax: Optional list of refund (CreditNote) counter dicts.

        Returns:
            tuple: (response_data with operationID, None) or (None, error_message).
        """
        status_data, err = self.get_status(device)
        if err:
            return None, f"GetStatus failed: {err}"
        status = status_data.get("fiscalDayStatus")
        if status not in ALLOWED_CLOSE_STATUSES:
            return None, f"Cannot close day: status must be FiscalDayOpened or FiscalDayCloseFailed (current: {status})"

        fiscal_day_no = device.last_fiscal_day_no
        if fiscal_day_no is None:
            return None, "No open fiscal day"
        if sale_by_tax or refund_by_tax:
            logger.warning("CloseDay payload should be built from receipts; ignoring provided counters.")

        last_receipt_no = status_data.get("lastReceiptGlobalNo")
        payload, payload_err = self._build_close_day_payload(
            device, fiscal_day_no, last_receipt_no
        )
        if payload_err:
            return None, payload_err

        body = _fdms_json_dumps(payload)
        logger.info("CloseDay request:\n%s", json.dumps(payload, indent=2, default=str))

        base_url = getattr(settings, "FDMS_BASE_URL", "").rstrip("/")
        device_id = device.device_id
        endpoint = f"/Device/v1/{device_id}/CloseDay"
        url = f"{base_url}{endpoint}"

        headers = self.headers()

        logger.info("FDMS Headers: %s", headers)
        try:
            with cert_files_for_device(device) as (cert_path, key_path):
                response = fdms_request(
                    "POST", url, data=body, headers=headers,
                    cert=(cert_path, key_path), timeout=30,
                )
        except ValueError as e:
            log_fdms_call(
                endpoint=endpoint,
                method="POST",
                request_payload=payload,
                error=str(e),
                tenant=getattr(device, "tenant", None),
            )
            return None, str(e)

        log_fdms_call(
            endpoint=endpoint,
            method="POST",
            request_payload=payload,
            response=response,
            tenant=getattr(device, "tenant", None),
        )

        if response.status_code != 200:
            try:
                err_body = response.json()
                logger.info("CloseDay response (error):\n%s", json.dumps(err_body, indent=2, default=str))
                detail = err_body.get("detail", err_body.get("title", response.text))
            except Exception:
                logger.info("CloseDay response (error): %s", response.text or "(empty)")
                detail = response.text or f"HTTP {response.status_code}"
            return None, detail

        data = response.json()
        logger.info("CloseDay response:\n%s", json.dumps(data, indent=2, default=str))
        device.fiscal_day_status = "FiscalDayCloseInitiated"
        device.save(update_fields=["fiscal_day_status"])
        logger.info("CloseDay initiated for device %s", device_id)
        return data, None

    def poll_until_closed(
        self,
        device: FiscalDevice,
        interval_seconds: int = 10,
        max_attempts: int = 60,
    ) -> tuple[str, str | None]:
        """
        Poll getStatus every interval_seconds until FiscalDayClosed or FiscalDayCloseFailed.

        Args:
            device: FiscalDevice.
            interval_seconds: Polling interval.
            max_attempts: Max polls before giving up.

        Returns:
            tuple: (final_status, error_or_none)
        """
        for _ in range(max_attempts):
            data, err = self.get_status(device)
            if err:
                return device.fiscal_day_status or "unknown", err
            status = data.get("fiscalDayStatus")
            if status in ("FiscalDayClosed", "FiscalDayCloseFailed"):
                if status == "FiscalDayClosed":
                    fiscal_day = FiscalDay.objects.filter(
                        device=device,
                        fiscal_day_no=device.last_fiscal_day_no,
                        status="FiscalDayOpened",
                    ).first()
                    if fiscal_day:
                        fiscal_day.status = "FiscalDayClosed"
                        fiscal_day.closed_at = datetime.now()
                        fiscal_day.save()
                return status, None
            time.sleep(interval_seconds)
        return device.fiscal_day_status or "unknown", "Polling timeout"
