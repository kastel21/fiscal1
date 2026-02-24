"""
FDMS credit/debit note reference. creditDebitNote includes receiptID (when available),
deviceID, receiptGlobalNo, fiscalDayNo. No receiptDate. RCPT032.
"""

from django.core.exceptions import ValidationError

from fiscal.models import Receipt


def build_credit_debit_reference(original_invoice: Receipt) -> dict:
    """
    Return creditDebitNote payload with receiptID, deviceID, receiptGlobalNo, fiscalDayNo.
    receiptID included when available; deviceID, receiptGlobalNo, fiscalDayNo always present.
    """
    if not original_invoice:
        raise ValidationError("Original invoice is required (RCPT032).")
    if original_invoice.receipt_global_no is None:
        raise ValidationError("Original invoice receiptGlobalNo is required (RCPT032).")
    if original_invoice.fiscal_day_no is None:
        raise ValidationError("Original invoice fiscalDayNo is required (RCPT032).")
    device = getattr(original_invoice, "device", None)
    if not device:
        raise ValidationError("Original invoice device is required (RCPT032).")
    fdms_device_id = getattr(device, "device_id", None)
    if fdms_device_id is None:
        raise ValidationError("Original invoice deviceID is required (RCPT032).")
    if original_invoice.device_id != device.pk:
        raise ValidationError("Original invoice deviceID mismatch (RCPT032).")

    out = {
        "deviceID": int(fdms_device_id),
        "receiptGlobalNo": int(original_invoice.receipt_global_no),
        "fiscalDayNo": int(original_invoice.fiscal_day_no),
    }
    receipt_id = getattr(original_invoice, "fdms_receipt_id", None) or getattr(
        original_invoice, "receipt_id", None
    )
    if receipt_id is not None and receipt_id != 0:
        out["receiptID"] = int(receipt_id)
    return out
