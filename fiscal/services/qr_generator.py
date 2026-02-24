"""
ZIMRA-compliant QR generation for fiscal receipts.
Format: qrUrl/deviceID(10)receiptDate(ddMMyyyy)receiptGlobalNo(10)receiptQrData(16)
"""

import base64
import hashlib
from io import BytesIO

import qrcode

ZIMRA_QR_URL = "https://invoice.zimra.co.zw"


def get_receipt_device_signature_hash_hex(receipt) -> str:
    """Derive hex of receiptDeviceSignature hash from receipt_hash (base64)."""
    sig_b64 = (receipt.receipt_hash or "").strip()
    if not sig_b64:
        return ""
    try:
        sig_bytes = base64.b64decode(sig_b64)
        return sig_bytes.hex()
    except Exception:
        return ""


def generate_receipt_qr_string(receipt):
    device_id = str(receipt.device.device_id).zfill(10)
    receipt_date = (receipt.receipt_date or receipt.created_at)
    if receipt_date:
        receipt_date = receipt_date.strftime("%d%m%Y")
    else:
        receipt_date = "01011970"
    receipt_global_no = str(receipt.receipt_global_no).zfill(10)
    signature_hex = receipt.receipt_device_signature_hash_hex.upper()
    if not signature_hex:
        return ""
    md5_hash = hashlib.md5(signature_hex.encode()).hexdigest().upper()
    receipt_qr_data = md5_hash[:16]
    return f"{ZIMRA_QR_URL}/{device_id}{receipt_date}{receipt_global_no}{receipt_qr_data}"


def generate_qr_base64(qr_string):
    if not qr_string:
        return ""
    try:
        qr = qrcode.make(qr_string)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""
