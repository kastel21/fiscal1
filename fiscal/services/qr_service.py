"""
ZIMRA Section 11 QR code value generation for fiscal receipts.
Format: qrUrl/ + deviceID(10) + receiptDate(ddMMyyyy) + receiptGlobalNo(10) + receiptQrData(16).
"""

import hashlib
import logging
import re
from datetime import date
from typing import TYPE_CHECKING

from fiscal.services.qr_generator import generate_receipt_qr_string

if TYPE_CHECKING:
    from fiscal.models import Receipt

logger = logging.getLogger("fiscal")


def generate_receipt_qr(
    qr_url: str,
    device_id: int,
    receipt_date: date,
    receipt_global_no: int,
    receipt_device_signature_hex: str,
) -> str:
    """Build ZIMRA deep link from components. receiptQrData = first 16 chars (uppercase) of MD5(hex)."""
    base = (qr_url or "").strip().rstrip("/") + "/"
    device_pad = str(device_id).zfill(10)
    date_str = receipt_date.strftime("%d%m%Y")
    global_pad = str(receipt_global_no).zfill(10)
    hex_sig = (receipt_device_signature_hex or "").strip()
    md5_hex = hashlib.md5(hex_sig.encode("utf-8")).hexdigest().upper()
    qr_data = (md5_hex[:16] if len(md5_hex) >= 16 else md5_hex.ljust(16))[:16]
    return f"{base}{device_pad}{date_str}{global_pad}{qr_data}"


def validate_qr_structure(qr_value: str) -> bool:
    """
    Verify ZIMRA QR string: URL present, then 10-digit device ID,
    8-digit date (ddMMyyyy), 10-digit receiptGlobalNo, 16-char hash fragment.
    """
    if not qr_value or not isinstance(qr_value, str):
        return False
    s = qr_value.strip()
    if not s.startswith("http://") and not s.startswith("https://"):
        return False
    # After last slash: 10 + 8 + 10 + 16 = 44 chars
    parts = s.split("/")
    suffix = parts[-1] if parts else ""
    pattern = r"^(\d{10})(\d{8})(\d{10})([0-9A-Fa-f]{16})$"
    return bool(re.match(pattern, suffix))


def attach_qr_to_receipt(receipt: "Receipt") -> None:
    """
    Generate ZIMRA QR deep link and set qr_code_value on receipt.
    Call only after FDMS SubmitReceipt has succeeded (signature and receipt_date set).
    Applies to FISCALINVOICE, CREDITNOTE, DEBITNOTE.
    """
    rt = (receipt.receipt_type or "").strip().upper()
    if rt not in ("FISCALINVOICE", "CREDITNOTE", "DEBITNOTE"):
        logger.debug(
            "QR skipped for receipt %s: receipt_type=%r not in (FISCALINVOICE, CREDITNOTE, DEBITNOTE)",
            receipt.receipt_global_no, receipt.receipt_type,
        )
        return
    qr_value = generate_receipt_qr_string(receipt)
    if not qr_value:
        # qr_code_value stays empty when receipt_hash is missing or invalid (signature hex required for QR)
        has_hash = bool((receipt.receipt_hash or "").strip())
        logger.warning(
            "QR empty for receipt %s: generate_receipt_qr_string returned empty. receipt_hash present=%s",
            receipt.receipt_global_no, has_hash,
        )
        return
    receipt.qr_code_value = qr_value
    receipt.save(update_fields=["qr_code_value"])
