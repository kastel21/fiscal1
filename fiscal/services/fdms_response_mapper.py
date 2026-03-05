"""
ZIMRA Section 10 – Map FDMS SubmitReceipt response to Receipt model fields.
Run after successful fiscalisation; then run VAT engine and set buyer from customer_snapshot.
All fields saved before marking invoice as final (FISCALISED).
"""

from decimal import Decimal

from fiscal.models import Receipt
from fiscal.services.vat_engine import compute_vat_breakdown


def map_fdms_response_to_receipt(receipt: Receipt, response_data: dict) -> dict:
    """
    Map FDMS response to Receipt fields. Returns dict of updates to apply (fiscal_invoice_number,
    receipt_number, fiscal_signature, verification_code, VAT breakdown, buyer).
    Does not save; caller should update receipt with these defaults or save.
    """
    out = {}
    # FDMS response mapping (Section 10)
    out["fiscal_invoice_number"] = (
        str(response_data.get("fiscalInvoiceNumber") or response_data.get("invoiceNo") or receipt.invoice_no or "")
    )[:80]
    if "receiptNumber" in response_data:
        out["receipt_number"] = str(response_data["receiptNumber"])[:80]
    # receipt_global_no / fiscal_day_no already set in submit flow; do not overwrite
    if "fiscalSignature" in response_data:
        out["fiscal_signature"] = str(response_data["fiscalSignature"])
    sig = response_data.get("receiptDeviceSignature") or {}
    if isinstance(sig, dict) and sig.get("hash"):
        out["fiscal_signature"] = out.get("fiscal_signature") or str(sig["hash"])
    if not out.get("fiscal_signature") and (receipt.receipt_hash or "").strip():
        out["fiscal_signature"] = (receipt.receipt_hash or "").strip()
    if "verificationCode" in response_data:
        out["verification_code"] = str(response_data["verificationCode"])[:80]
    server_sig = response_data.get("receiptServerSignature") or {}
    if isinstance(server_sig, dict) and server_sig.get("verificationCode"):
        out["verification_code"] = out.get("verification_code") or str(server_sig["verificationCode"])[:80]

    # VAT engine: compute breakdown from receipt_lines and receipt_taxes
    receipt_total = receipt.receipt_total
    breakdown = compute_vat_breakdown(
        receipt.receipt_lines or [],
        receipt.receipt_taxes or [],
        receipt_total,
    )
    out["subtotal_15"] = breakdown["subtotal_15"]
    out["tax_15"] = breakdown["tax_15"]
    out["subtotal_0"] = breakdown["subtotal_0"]
    out["subtotal_exempt"] = breakdown["subtotal_exempt"]
    out["total_tax"] = breakdown["total_tax"]
    # total is receipt_total; no separate field

    # Buyer from customer_snapshot
    snap = receipt.customer_snapshot or {}
    out["buyer_name"] = str(snap.get("name") or "")[:255]
    out["buyer_vat"] = str(snap.get("vat_number") or snap.get("VATNumber") or "")[:50]
    out["buyer_tin"] = str(snap.get("tin") or "")[:50]
    addr = snap.get("address")
    if isinstance(addr, dict):
        from fiscal.services.invoice_layout_service import _format_address
        out["buyer_address"] = _format_address(addr)
    else:
        out["buyer_address"] = str(addr or "")[:2000]

    return out


def apply_fdms_response_to_receipt(receipt: Receipt, response_data: dict) -> None:
    """
    Map FDMS response to receipt, update VAT breakdown and buyer, then save.
    Call after successful SubmitReceipt (200) before marking as final.
    """
    updates = map_fdms_response_to_receipt(receipt, response_data)
    valid = [k for k in updates if hasattr(Receipt, k)]
    for key in valid:
        setattr(receipt, key, updates[key])
    receipt.save(update_fields=valid)
