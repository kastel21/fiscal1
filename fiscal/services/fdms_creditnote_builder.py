"""
FDMS Credit Note payload builder. creditDebitNote (receiptID or deviceID+receiptGlobalNo+fiscalDayNo).
RCPT015, RCPT022, RCPT023, RCPT032-RCPT036, RCPT043, RCPT034. Decimal only, ROUND_HALF_UP.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.fdms_reference_builder import build_credit_debit_reference
from fiscal.services.invoice_credit_service import validate_credit_against_invoice

CREDIT_MAX_AGE_MONTHS = 12


def _d(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_cents(value: Decimal) -> int:
    return int((_round2(value) * 100).to_integral_value())


def validate_credit_note_preconditions(
    device: FiscalDevice,
    original_invoice: Receipt,
    credit_total: Decimal,
    reason: str,
) -> None:
    if not original_invoice:
        raise ValidationError("Original invoice is required (RCPT032).")
    if not original_invoice.fdms_receipt_id:
        raise ValidationError("Original invoice must be fiscalised.")
    doc_type = getattr(original_invoice, "document_type", "INVOICE")
    if doc_type not in ("INVOICE", ""):
        raise ValidationError("Cannot credit a credit or debit note.")
    rt = (original_invoice.receipt_type or "").strip().upper()
    if rt not in ("FISCALINVOICE",):
        raise ValidationError("Selected document is not an invoice.")
    if original_invoice.credit_status == "FULLY_CREDITED":
        raise ValidationError("Cannot credit a fully credited invoice.")
    validate_credit_against_invoice(original_invoice, credit_total)
    if original_invoice.device_id != device.pk:
        raise ValidationError("Original invoice belongs to a different device (RCPT032).")
    if not (reason and str(reason).strip()):
        raise ValidationError("Credit/debit reason is required (RCPT034).")
    if not (original_invoice.currency or str(original_invoice.currency).strip()):
        raise ValidationError("Original invoice currency is required (RCPT043).")
    if original_invoice.receipt_date:
        now = datetime.now(timezone.utc)
        rec_dt = original_invoice.receipt_date
        if rec_dt.tzinfo is None:
            rec_dt = rec_dt.replace(tzinfo=timezone.utc)
        if (now - rec_dt).days > CREDIT_MAX_AGE_MONTHS * 30:
            raise ValidationError(
                f"Original invoice must not be older than {CREDIT_MAX_AGE_MONTHS} months (RCPT033)."
            )


def _validate_credit_note_tax_ids(original_invoice: Receipt, receipt_lines_in: list, receipt_taxes_in: list) -> None:
    orig_tax_ids = {int(t.get("taxID")) for t in (original_invoice.receipt_taxes or []) if t.get("taxID") is not None}
    if not orig_tax_ids:
        orig_tax_ids = {1}
    for ln in receipt_lines_in or []:
        tid = ln.get("taxID")
        if tid is not None and int(tid) not in orig_tax_ids:
            raise ValidationError(
                f"Tax ID {tid} in credit note does not exist on original invoice (RCPT036)."
            )
    for t in receipt_taxes_in or []:
        tid = t.get("taxID")
        if tid is not None and int(tid) not in orig_tax_ids:
            raise ValidationError(
                f"Tax ID {tid} in credit note does not exist on original invoice (RCPT036)."
            )


def build_creditnote_payload(
    device: FiscalDevice,
    credit_note: dict,
    original_invoice: Receipt,
) -> dict:
    """
    Build FDMS Credit Note payload: positive quantity, negative price/total/tax/payment.

    FDMS requirement for credit notes:
    - receiptTaxes.taxAmount must be negative
    - receiptTaxes.salesAmountWithTax must be negative
    - paymentAmount must be negative

    Includes creditDebitNote (receiptID or deviceID+receiptGlobalNo+fiscalDayNo) and receiptNotes.
    Decimal only, ROUND_HALF_UP. RCPT032-RCPT036, RCPT043 validated.
    credit_note: dict with keys receipt_lines, receipt_taxes, credit_total (positive), reason.
    """
    receipt_lines_in = credit_note.get("receipt_lines") or []
    receipt_taxes_in = credit_note.get("receipt_taxes") or []
    credit_total_pos = _d(credit_note.get("credit_total") or credit_note.get("receipt_total") or 0)
    reason = (credit_note.get("reason") or "").strip()
    validate_credit_note_preconditions(device, original_invoice, credit_total_pos, reason)
    _validate_credit_note_tax_ids(original_invoice, receipt_lines_in, receipt_taxes_in)

    receipt_lines_out = []
    for i, ln in enumerate(receipt_lines_in):
        line_total_pos = _d(ln.get("receiptLineTotal") or ln.get("lineAmount") or 0)
        qty_raw = ln.get("receiptLineQuantity") or ln.get("quantity") or 1
        qty = _round2(_d(qty_raw))
        if qty <= 0:
            qty = Decimal("1.00")
        unit_price_pos = line_total_pos / qty if qty else Decimal("0")
        unit_price_neg = -_round2(unit_price_pos)
        line_total_neg = _round2(qty * unit_price_neg)
        receipt_lines_out.append({
            "receiptLineNo": i + 1,
            "receiptLineQuantity": float(qty),
            "receiptLinePrice": unit_price_neg,
            "receiptLineTotal": line_total_neg,
            "receiptLineName": str(ln.get("receiptLineName") or "Credit")[:200],
            "receiptLineHSCode": str(ln.get("receiptLineHSCode") or ln.get("hs_code") or "0000")[:8],
            "receiptLineType": ln.get("receiptLineType") or "Sale",
            "taxID": ln.get("taxID", 1),
            "taxCode": str(ln.get("taxCode") or "1")[:20],
            "taxPercent": round(float(ln.get("taxPercent", 0)), 2),
        })

    receipt_total_neg = sum((ln["receiptLineTotal"] for ln in receipt_lines_out), Decimal("0"))

    taxes_out = []
    for t in receipt_taxes_in:
        tax_amt_pos = _d(t.get("taxAmount") or 0)
        sales_pos = _d(t.get("salesAmountWithTax") or 0)
        taxes_out.append({
            "taxID": t.get("taxID", 1),
            "taxCode": str(t.get("taxCode") or "1")[:20],
            "taxPercent": round(float(t.get("taxPercent") or 0), 2),
            "taxAmount": -_round2(abs(tax_amt_pos)),
            "salesAmountWithTax": -_round2(abs(sales_pos)),
        })

    receipt_total_cents = _to_cents(receipt_total_neg)
    sum_tax_sales_cents = sum(_to_cents(t["salesAmountWithTax"]) for t in taxes_out)
    if taxes_out and sum_tax_sales_cents != receipt_total_cents:
        diff_cents = receipt_total_cents - sum_tax_sales_cents
        taxes_out[-1]["salesAmountWithTax"] = _round2(
            taxes_out[-1]["salesAmountWithTax"] + (Decimal(diff_cents) / 100)
        )

    payments_in = credit_note.get("receipt_payments")
    if not payments_in:
        method = str(credit_note.get("refund_method") or "CASH").strip().upper()
        if method == "OFFSET":
            method = "CREDIT"
        payments_out = [{"paymentAmount": receipt_total_neg, "method": method}]
    else:
        payments_out = []
        for p in payments_in:
            amt = _d(p.get("paymentAmount") or p.get("amount") or 0)
            method = str(p.get("method") or p.get("moneyType") or "CASH").strip().upper()
            if method == "OFFSET":
                method = "CREDIT"
            payments_out.append({"paymentAmount": -_round2(abs(amt)), "method": method})
        pay_sum_cents = sum(_to_cents(p["paymentAmount"]) for p in payments_out)
        if pay_sum_cents != receipt_total_cents and payments_out:
            payments_out[-1]["paymentAmount"] = _round2(
                receipt_total_neg - sum(p["paymentAmount"] for p in payments_out[:-1])
            )

    credit_debit_note = build_credit_debit_reference(original_invoice)

    return {
        "receipt_lines": receipt_lines_out,
        "receipt_taxes": taxes_out,
        "receipt_payments": payments_out,
        "receipt_total": receipt_total_neg,
        "credit_debit_note": credit_debit_note,
        "receipt_notes": reason,
    }
