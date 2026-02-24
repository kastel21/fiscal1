"""
FDMS Debit Note payload builder. All values POSITIVE. referencedReceipt and receiptNotes.
RCPT030, RCPT032, RCPT033, RCPT034 compliant. Decimal only, ROUND_HALF_UP.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.debit_validation import validate_debit_note
from fiscal.services.fdms_reference_builder import build_credit_debit_reference
from fiscal.services.tax_calculator import extract_net_from_inclusive, extract_tax_from_inclusive


def _d(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


DEBIT_MAX_AGE_MONTHS = 12


def validate_debit_note_preconditions(
    device: FiscalDevice,
    original_invoice: Receipt,
    debit_total: Decimal,
    reason: str,
) -> None:
    if not original_invoice:
        raise ValidationError("Original invoice is required.")
    if not original_invoice.fdms_receipt_id:
        raise ValidationError("Original invoice must be fiscalised.")
    doc_type = getattr(original_invoice, "document_type", "INVOICE")
    if doc_type not in ("INVOICE", ""):
        raise ValidationError("Debit note cannot reference a credit or debit note.")
    rt = (original_invoice.receipt_type or "").strip().upper()
    if rt not in ("FISCALINVOICE",):
        raise ValidationError("Selected document is not an invoice.")
    if rt == "CREDITNOTE":
        raise ValidationError("Cannot debit a credit note.")
    if original_invoice.device_id != device.pk:
        raise ValidationError("Original invoice belongs to a different device.")
    if debit_total <= 0:
        raise ValidationError("Debit amount must be greater than zero.")
    if not (reason and str(reason).strip()):
        raise ValidationError("Credit/debit reason is required (RCPT034).")
    if original_invoice.receipt_global_no is None or original_invoice.fiscal_day_no is None:
        raise ValidationError("Original invoice must have receiptGlobalNo and fiscalDayNo (RCPT032).")
    now = datetime.now(timezone.utc)
    rec_dt = original_invoice.receipt_date
    if rec_dt.tzinfo is None:
        rec_dt = rec_dt.replace(tzinfo=timezone.utc)
    months_ago = (now - rec_dt).days / 30
    if months_ago > DEBIT_MAX_AGE_MONTHS:
        raise ValidationError(
            f"Invoice must not be older than {DEBIT_MAX_AGE_MONTHS} months (RCPT033)."
        )


def build_debitnote_payload(
    device: FiscalDevice,
    debit_note: dict,
    original_invoice: Receipt,
) -> dict:
    """
    Build FDMS Debit Note payload: all positive quantity, price, totals, tax, payment.
    Includes referencedReceipt and receiptNotes. Decimal only, ROUND_HALF_UP.
    debit_note: dict with keys debit_lines (or receipt_lines), debit_total, reason.
    """
    debit_lines_in = debit_note.get("debit_lines") or debit_note.get("receipt_lines") or []
    debit_total_pos = _d(debit_note.get("debit_total") or debit_note.get("receipt_total") or 0)
    reason = (debit_note.get("reason") or "").strip()
    validate_debit_note_preconditions(device, original_invoice, debit_total_pos, reason)

    orig_taxes = original_invoice.receipt_taxes or []
    orig_tax_ids = original_invoice.get_tax_ids()
    try:
        validate_debit_note(
            original_receipt=original_invoice,
            debit_total=debit_total_pos,
            tax_ids=orig_tax_ids,
            currency=original_invoice.currency or "USD",
        )
    except ValueError as e:
        raise ValidationError(str(e))
    if not orig_taxes:
        orig_taxes = [{
            "taxID": 1,
            "taxCode": "VAT",
            "taxPercent": Decimal("0"),
            "salesAmountWithTax": original_invoice.receipt_total or 0,
            "taxAmount": Decimal("0"),
        }]

    tax_id = int(orig_taxes[0].get("taxID", 1))
    tax_code = str(orig_taxes[0].get("taxCode") or "VAT")[:20]
    tax_pct = _d(orig_taxes[0].get("taxPercent") or orig_taxes[0].get("fiscalCounterTaxPercent") or 0)
    tax_pct_float = round(float(tax_pct), 2)

    receipt_lines_out = []
    for i, ln in enumerate(debit_lines_in):
        line_total = _d(ln.get("line_total") or ln.get("receiptLineTotal") or ln.get("amount") or 0)
        qty_raw = ln.get("quantity") or ln.get("receiptLineQuantity") or 1
        qty = _round2(_d(qty_raw))
        if qty <= 0:
            qty = Decimal("1.00")
        unit_price = _round2(line_total / qty) if qty else Decimal("0")
        line_total_rounded = _round2(qty * unit_price)
        receipt_lines_out.append({
            "receiptLineNo": i + 1,
            "receiptLineQuantity": float(qty),
            "receiptLinePrice": unit_price,
            "receiptLineTotal": line_total_rounded,
            "receiptLineName": str(ln.get("description") or ln.get("receiptLineName") or "Debit")[:200],
            "receiptLineHSCode": str(ln.get("receiptLineHSCode") or ln.get("hs_code") or "0000")[:8],
            "receiptLineType": ln.get("receiptLineType") or "Sale",
            "taxID": tax_id,
            "taxCode": tax_code,
            "taxPercent": tax_pct_float,
        })

    if not receipt_lines_out:
        raise ValidationError("At least one debit line is required.")
    net_total = sum((ln["receiptLineTotal"] for ln in receipt_lines_out), Decimal("0"))
    if net_total <= 0:
        raise ValidationError("Debit total must be greater than zero.")

    hundred = Decimal("100")
    if tax_pct > 0:
        receipt_total_pos = _round2(net_total * (1 + tax_pct / hundred))
        tax_amount = extract_tax_from_inclusive(receipt_total_pos, tax_pct)
        net_from_incl = extract_net_from_inclusive(receipt_total_pos, tax_pct)
        if net_from_incl + tax_amount != receipt_total_pos:
            tax_amount = (receipt_total_pos - net_from_incl).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
    else:
        tax_amount = Decimal("0")
        receipt_total_pos = net_total

    taxes_out = [{
        "taxID": tax_id,
        "taxCode": tax_code,
        "taxPercent": tax_pct_float,
        "taxAmount": tax_amount,
        "salesAmountWithTax": receipt_total_pos,
    }]

    if len(orig_taxes) > 1:
        orig_total = _d(original_invoice.receipt_total or 0)
        if orig_total > 0:
            taxes_out = []
            for t in orig_taxes:
                band_sales = _d(t.get("salesAmountWithTax") or t.get("fiscalCounterValue") or 0)
                if band_sales <= 0:
                    continue
                ratio = band_sales / orig_total
                allocated = _round2(receipt_total_pos * ratio)
                pct = _d(t.get("taxPercent") or t.get("fiscalCounterTaxPercent") or 0)
                pct_f = round(float(pct), 2)
                if pct > 0:
                    tax_band = extract_tax_from_inclusive(allocated, _d(pct))
                    net_band = extract_net_from_inclusive(allocated, _d(pct))
                    if net_band + tax_band != allocated:
                        tax_band = (allocated - net_band).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                else:
                    net_band = allocated
                    tax_band = Decimal("0")
                taxes_out.append({
                    "taxID": int(t.get("taxID", 1)),
                    "taxCode": str(t.get("taxCode") or "VAT")[:20],
                    "taxPercent": pct_f,
                    "taxAmount": tax_band,
                    "salesAmountWithTax": allocated,
                })
            sum_tax_sales = sum(t["salesAmountWithTax"] for t in taxes_out)
            if sum_tax_sales != receipt_total_pos and taxes_out:
                diff = receipt_total_pos - sum_tax_sales
                taxes_out[-1]["salesAmountWithTax"] = _round2(taxes_out[-1]["salesAmountWithTax"] + diff)
                pct_last = _d(orig_taxes[-1].get("taxPercent") or 0)
                if pct_last > 0:
                    new_alloc = taxes_out[-1]["salesAmountWithTax"]
                    taxes_out[-1]["taxAmount"] = extract_tax_from_inclusive(
                        new_alloc, pct_last
                    )
                else:
                    taxes_out[-1]["taxAmount"] = Decimal("0")

    payments_in = debit_note.get("receipt_payments")
    if not payments_in:
        payments_out = [{"paymentAmount": receipt_total_pos, "method": "CASH"}]
    else:
        payments_out = []
        for p in payments_in:
            amt = _d(p.get("paymentAmount") or p.get("amount") or 0)
            method = str(p.get("method") or p.get("moneyType") or "CASH").strip().upper()
            payments_out.append({"paymentAmount": _round2(abs(amt)), "method": method})
        pay_sum = sum(p["paymentAmount"] for p in payments_out)
        if pay_sum != receipt_total_pos and payments_out:
            payments_out[-1]["paymentAmount"] = _round2(
                receipt_total_pos - sum(p["paymentAmount"] for p in payments_out[:-1])
            )

    credit_debit_note = build_credit_debit_reference(original_invoice)

    return {
        "receipt_lines": receipt_lines_out,
        "receipt_taxes": taxes_out,
        "receipt_payments": payments_out,
        "receipt_total": receipt_total_pos,
        "credit_debit_note": credit_debit_note,
        "receipt_notes": reason,
    }
