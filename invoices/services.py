"""
Invoice creation service. FDMS v7.2 compliant.
Builds receipt from items (no product linkage). Tax from dropdown only: 0% and 15.5%.
Never uses GetConfig for tax. Raises error if tax missing or invalid.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.config_service import get_config_status, get_latest_configs
from fiscal.services.receipt_service import resolve_receipt_type, submit_receipt

ALLOWED_TAXES = {1: (0.0, "1"), 2: (0.0, "2"), 517: (15.5, "517")}


def _to_cents(value) -> int:
    return int(
        (Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100).to_integral_value()
    )


def _build_receipt_from_items(
    validated: dict,
    device: FiscalDevice,
) -> tuple[list, list, list, float, str | None]:
    """
    Build receipt_lines, receipt_taxes, receipt_payments from validated items.
    Tax from dropdown only (0% or 15.5%). Never GetConfig. Raise error if tax missing.
    Returns (receipt_lines, receipt_taxes, receipt_payments, grand_total, error_message).
    """
    receipt_lines = []
    tax_subtotals = defaultdict(Decimal)

    for it in validated["items"]:
        tax_percent = it.get("tax_percent")
        tax_code = (it.get("tax_code") or "").strip()[:3]
        tax_id = it.get("tax_id")
        if tax_id is None:
            return [], [], [], 0, "Missing tax. Select 0% or 15.5% for each item."
        tid_int = int(tax_id)
        if tid_int not in ALLOWED_TAXES:
            return [], [], [], 0, f"Invalid tax_id {tid_int}. Allowed: 1, 2 (0%), 517 (15.5%)."
        allowed_pct, allowed_code = ALLOWED_TAXES[tid_int]
        if tax_percent is None:
            return [], [], [], 0, "Missing tax_percent. Select 0% or 15.5% for each item."
        tax_pct = float(tax_percent)
        if tax_pct not in (0.0, 15.5):
            return [], [], [], 0, f"Invalid tax {tax_pct}%. Use 0% or 15.5% only."
        tax_code = tax_code or allowed_code

        qty = float(it["quantity"])
        unit_price = float(it["unit_price"])
        line_subtotal_dec = (Decimal(str(qty)) * Decimal(str(unit_price))).quantize(Decimal("0.01"), ROUND_HALF_UP)
        item_name = (it.get("item_name") or "Item")[:200]
        hs_code = str(it.get("hs_code") or "").strip() or "000000"

        receipt_lines.append({
            "receiptLineType": "Sale",
            "receiptLineName": item_name,
            "receiptLineQuantity": qty,
            "receiptLinePrice": float(unit_price),
            "receiptLineTotal": float(line_subtotal_dec),
            "receiptLineTaxCode": tax_code,
            "receiptLineHSCode": hs_code[:8] if hs_code else "000000",
            "taxID": tid_int,
        })
        key = (tid_int, tax_code, tax_pct)
        tax_subtotals[key] += line_subtotal_dec

    receipt_taxes = []
    for (tid_int, tax_code, tax_pct), subtotal_band in sorted(tax_subtotals.items()):
        raw_tax = subtotal_band * Decimal(str(tax_pct)) / Decimal("100")
        tax_amount = raw_tax.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
        sales_with_tax = (subtotal_band + tax_amount).quantize(Decimal("0.01"), ROUND_HALF_UP)
        receipt_taxes.append({
            "taxID": tid_int,
            "taxCode": tax_code,
            "taxPercent": round(float(tax_pct), 2),
            "taxAmount": int(_to_cents(tax_amount)),
            "salesAmountWithTax": float(sales_with_tax),
        })

    subtotal_dec = sum(Decimal(str(line["receiptLineTotal"])) for line in receipt_lines)
    total_tax_cents = sum(t["taxAmount"] for t in receipt_taxes)
    grand_total_dec = (subtotal_dec + Decimal(total_tax_cents) / Decimal("100")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    grand_total = float(grand_total_dec)
    receipt_payments = []
    for p in validated["payments"]:
        amt = Decimal(str(p["amount"])).quantize(Decimal("0.01"), ROUND_HALF_UP)
        if amt > 0:
            receipt_payments.append({
                "moneyType": str(p["method"]).upper(),
                "paymentAmount": float(amt),
            })
    payment_total = sum(Decimal(str(p["paymentAmount"])) for p in receipt_payments)
    shortfall = grand_total_dec - payment_total
    if shortfall > Decimal("0") and receipt_payments:
        # Underpayment: add shortfall to first payment
        first = receipt_payments[0]
        first["paymentAmount"] = float(
            (Decimal(str(first["paymentAmount"])) + shortfall).quantize(Decimal("0.01"), ROUND_HALF_UP)
        )
    elif shortfall < Decimal("0") and receipt_payments:
        # Overpayment: trim last payment so total equals grand total
        excess = -shortfall
        for i in range(len(receipt_payments) - 1, -1, -1):
            amt = Decimal(str(receipt_payments[i]["paymentAmount"]))
            if amt >= excess:
                receipt_payments[i]["paymentAmount"] = float(
                    (amt - excess).quantize(Decimal("0.01"), ROUND_HALF_UP)
                )
                if receipt_payments[i]["paymentAmount"] == 0:
                    receipt_payments.pop(i)
                break
            excess -= amt
            receipt_payments.pop(i)
    if not receipt_payments:
        receipt_payments = [{"moneyType": "CASH", "paymentAmount": grand_total}]

    return receipt_lines, receipt_taxes, receipt_payments, grand_total, None  # grand_total is 2-decimal float


def create_invoice(validated: dict) -> tuple[Receipt | None, str | None]:
    """
    Create and submit invoice to FDMS.
    No product linkage. Tax from dropdown only (0% or 15.5%). Never GetConfig.
    Returns (Receipt, None) on success, (None, error_message) on failure.
    """
    device = FiscalDevice.objects.filter(
        device_id=validated["device_id"],
        is_registered=True,
    ).first()
    if not device:
        return None, "Device not found or not registered"
    if not device.is_vat_registered:
        for it in validated["items"]:
            pct = it.get("tax_percent")
            if pct is None:
                pct = ALLOWED_TAXES.get(int(it.get("tax_id") or -1), (0.0, ""))[0]
            if float(pct) > 0:
                return None, (
                    "Device is not VAT registered. Use 0% tax only, or register a VAT-registered device."
                )
    config_status = get_config_status(device.device_id)
    if config_status["status"] != "OK":
        return None, "FDMS configs missing or stale. Refresh configs before submitting."
    fiscal_day_no = device.last_fiscal_day_no
    if fiscal_day_no is None:
        return None, "No fiscal day open. Open fiscal day first."
    if device.fiscal_day_status not in ("FiscalDayOpened", "FiscalDayCloseFailed"):
        return None, f"Fiscal day must be open. Current status: {device.fiscal_day_status}"

    receipt_lines, receipt_taxes, receipt_payments, grand_total, build_err = _build_receipt_from_items(
        validated, device
    )
    if build_err:
        return None, build_err

    # Payments are auto-adjusted in _build_receipt_from_items to match grand total
    # Tax validation skipped: invoice creation uses fixed 0% / 15.5%, not GetConfig

    invoice_no = ""  # Auto-assign INV-yyyy-N format in receipt_service

    issue_tax_invoice = validated.get("issue_tax_invoice", True)
    receipt_type = resolve_receipt_type(issue_tax_invoice)

    customer_snapshot = None
    if receipt_type == "FISCALINVOICE":
        customer_snapshot = {
            "name": validated.get("customer_name", ""),
            "tin": validated.get("customer_tin", ""),
            "address": validated.get("customer_address", ""),
            "vat_number": validated.get("customer_vat_number", ""),
            "phone": validated.get("customer_phone", ""),
            "email": validated.get("customer_email", ""),
            "reference": "",
            "notes": validated.get("notes", ""),
        }

    receipt_obj, err = submit_receipt(
        device=device,
        fiscal_day_no=int(fiscal_day_no),
        receipt_type=receipt_type,
        receipt_currency=validated["currency"],
        invoice_no=invoice_no[:50] if invoice_no else "",
        receipt_lines=receipt_lines,
        receipt_taxes=receipt_taxes,
        receipt_payments=receipt_payments,
        receipt_total=grand_total,
        receipt_lines_tax_inclusive=False,
        customer_snapshot=customer_snapshot,
        tax_from_request_only=True,
    )
    return receipt_obj, err
