"""
SubmitReceipt service - FDMS v7.2 compliant.
Phase 06 Error Recovery:
- Retry for network failures (http_client + application-level)
- Idempotent receipt submission (invoice_no + fiscal_day_no, duplicate receiptGlobalNo)
- Detect duplicate receiptGlobalNo
- Re-sync with GetStatus before every submission
- Never auto-resubmit without verifying lastReceiptGlobalNo
"""

import copy
import json
import logging
import re
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Callable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from fiscal.models import FiscalDevice, Receipt
from fiscal.utils import mask_sensitive_fields, redact_string_for_log
from fiscal.services.config_service import (
    TAX_CODE_MAX_LENGTH,
    configs_are_fresh,
    enrich_receipt_taxes_with_tax_id,
    get_latest_configs,
    get_local_code_to_fdms_tax,
    get_tax_id_to_code,
    get_tax_id_to_percent,
    get_tax_table_from_configs,
    validate_against_configs,
)
from fiscal.services.fdms_device_service import FDMSDeviceService
from fiscal.services.receipt_engine import build_receipt_canonical_string, sign_receipt
from fiscal.services.tax_engine import calculate_receipt_totals
from fiscal.services.tax_mapper import (
    get_exempt_tax_ids,
    validate_hs_code_for_vat_taxpayer,
    validate_tax_combination,
)

logger = logging.getLogger("fiscal")

MAX_SUBMIT_RETRIES = 3


def _persist_invoice_pdf_if_enabled(receipt_obj: Receipt, receipt_global_no: int) -> bool:
    """
    Optionally persist generated PDF to Receipt.pdf_file.
    Disabled by default for on-demand generation.
    TODO: remove Receipt.pdf_file field in a later migration window.
    """
    if not getattr(settings, "FDMS_PERSIST_PDF", False):
        logger.info(
            "InvoiceA4 PDF persistence disabled (on-demand mode) for receipt %s",
            receipt_global_no,
        )
        return False

    try:
        from django.core.files.base import ContentFile
        from fiscal.services.pdf_generator import generate_fiscal_invoice_pdf

        receipt_obj.refresh_from_db()
        pdf_bytes = generate_fiscal_invoice_pdf(receipt_obj)
        filename = f"{receipt_obj.fdms_receipt_id or receipt_global_no}.pdf"
        receipt_obj.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
        logger.info("InvoiceA4 PDF saved for receipt %s: %s", receipt_global_no, filename)
        return True
    except Exception as e:
        logger.warning("InvoiceA4 PDF generation failed for receipt %s: %s", receipt_global_no, e)
        return False


def _cents_to_decimal(cents) -> float:
    """Convert cents (int) to decimal amount with 2 decimal places."""
    return round(float(cents) / 100, 2)


def _format_to_2_decimals(val) -> float:
    """Round to 2 decimal places."""
    if val is None:
        return val
    return round(float(val), 2)


def _payload_amounts_to_decimals(receipt_dto: dict) -> dict:
    """Convert cent-based amounts to decimal; ensure all monetary/quantity values have 2 decimal places."""
    dto = json.loads(json.dumps(receipt_dto, default=str))
    for ln in dto.get("receiptLines") or []:
        for k in ("receiptLinePrice", "receiptLineTotal"):
            if k in ln and ln[k] is not None:
                ln[k] = _format_to_2_decimals(float(ln[k]) / 100)
        if "receiptLineQuantity" in ln and ln["receiptLineQuantity"] is not None:
            ln["receiptLineQuantity"] = _format_to_2_decimals(ln["receiptLineQuantity"])
    for t in dto.get("receiptTaxes") or []:
        for k in ("taxAmount", "salesAmountWithTax"):
            if k in t and t[k] is not None:
                t[k] = _format_to_2_decimals(float(t[k]) / 100)
        if "taxPercent" in t and t["taxPercent"] is not None:
            t["taxPercent"] = _format_to_2_decimals(t["taxPercent"])
    for p in dto.get("receiptPayments") or []:
        if "paymentAmount" in p and p["paymentAmount"] is not None:
            p["paymentAmount"] = _format_to_2_decimals(float(p["paymentAmount"]) / 100)
    if "receiptTotal" in dto and dto["receiptTotal"] is not None:
        dto["receiptTotal"] = _format_to_2_decimals(float(dto["receiptTotal"]) / 100)
    return dto


def _format_amounts_in_json(body: str, keys: tuple) -> str:
    """Ensure numeric values for given keys are formatted with exactly 2 decimal places in JSON string."""
    def repl(m):
        return m.group(1) + format(round(float(m.group(2)), 2), ".2f")
    for key in keys:
        body = re.sub(
            rf'("{re.escape(key)}"\s*:\s*)(\d+(?:\.\d*)?)',
            repl,
            body,
        )
    return body


def _fdms_json_dumps(payload: dict) -> str:
    """Serialize payload to JSON with all monetary values formatted to 2 decimal places."""
    receipt = payload.get("receipt")
    if receipt:
        payload = {"receipt": _payload_amounts_to_decimals(receipt)}
    body = json.dumps(payload, indent=2, default=str)
    amount_keys = (
        "fiscalCounterTaxPercent",
        "receiptLinePrice", "receiptLineTotal", "receiptLineQuantity",
        "taxAmount", "salesAmountWithTax", "paymentAmount", "receiptTotal",
    )
    body = _format_amounts_in_json(body, amount_keys)
    return body


_MONEY_TYPE_MAP = {
    "CASH": "Cash",
    "CARD": "Card",
    "MOBILE": "MobileWallet",
    "MOBILEWALLET": "MobileWallet",
    "ECOCASH": "MobileWallet",
    "COUPON": "Coupon",
    "CREDIT": "Credit",
    "BANK_TRANSFER": "BankTransfer",
    "BANKTRANSFER": "BankTransfer",
    "OTHER": "Other",
}


def round2(value: Decimal | float | str) -> Decimal:
    """Round to 2 decimals with ROUND_HALF_UP (FDMS receipt fix pack). Never manually type amounts."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round2_vat(value: Decimal | float | str) -> Decimal:
    """Round to 2 decimals with ROUND_CEILING (round up) for VAT/tax calculations."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def to_cents(value: Decimal | float | str) -> int:
    """Convert monetary value to cents (integer). Never send decimals to FDMS."""
    return int((round2(value) * 100).to_integral_value())


def re_sync_device_from_get_status(device: FiscalDevice) -> tuple[dict | None, str | None]:
    """
    Re-sync device state from FDMS GetStatus. Updates device in DB.
    Returns (status_data, None) or (None, error_message).
    """
    service = FDMSDeviceService()
    try:
        status_data = service.get_status(device)
        return status_data, None
    except Exception as e:
        logger.warning("GetStatus re-sync failed for device %s: %s", device.device_id, e)
        return None, str(e)


def _validate_credit_note(
    device: FiscalDevice,
    original_invoice_no: str,
    original_receipt_global_no: int | None,
) -> str | None:
    """
    Validate credit note original reference. Returns error message or None if valid.
    Original invoice must exist and be fiscalized.
    """
    if not (original_invoice_no and original_invoice_no.strip()):
        return "Original invoice number is required for Credit Note"
    if original_receipt_global_no is None:
        return "Original receipt global number is required for Credit Note"
    orig = Receipt.objects.filter(
        device=device,
        receipt_global_no=int(original_receipt_global_no),
    ).first()
    if not orig:
        return f"Original receipt (global no {original_receipt_global_no}) not found"
    if not orig.fdms_receipt_id:
        return f"Original receipt {original_receipt_global_no} is not fiscalized"
    return None


def _transform_to_credit_note(
    receipt_lines: list[dict],
    receipt_taxes: list[dict],
    receipt_payments: list[dict],
    receipt_total: float,
) -> tuple[list[dict], list[dict], list[dict], float]:
    """
    Transform monetary values to negative for Credit Note. Returns copies.
    FDMS requires receiptLineQuantity > 0; only price, total, tax, payment are negative.
    """
    lines = copy.deepcopy(receipt_lines)
    taxes = copy.deepcopy(receipt_taxes)
    payments = copy.deepcopy(receipt_payments)
    for line in lines:
        # Keep quantity positive (FDMS: receiptLineQuantity must be greater than 0)
        for k in ("receiptLineTotal", "lineAmount", "lineTotal", "amount"):
            if k in line and line[k] is not None:
                line[k] = -abs(float(line[k]))
    for tax in taxes:
        for k in ("taxAmount",):
            if k in tax and tax[k] is not None:
                tax[k] = -abs(float(tax[k]))
        for k in ("salesAmountWithTax",):
            if k in tax and tax[k] is not None:
                tax[k] = -abs(float(tax[k]))
    for pay in payments:
        for k in ("paymentAmount", "amount"):
            if k in pay and pay[k] is not None:
                pay[k] = -abs(float(pay[k]))
    total = -abs(float(receipt_total))
    return lines, taxes, payments, total


def _recalculate_receipt_server_side(
    receipt_lines: list[dict],
    configs,
    receipt_lines_tax_inclusive: bool,
    local_to_fdms: dict,
    code_to_tax_id: dict,
    default_tax_id: int,
    tax_id_to_code: dict,
    tax_id_to_percent: dict,
    strict_tax: bool = False,
) -> tuple[list[dict], list[dict], Decimal]:
    """
    Recalculate all monetary values server-side. FDMS-compliant: aggregate first,
    tax once per group, round once. receiptTotal = SUM(salesAmountWithTax).
    """
    lines_out = []
    subtotal_by_tax = {}
    line_entries = []

    for i, line in enumerate(receipt_lines):
        ln = dict(line)
        qty = Decimal(str(ln.get("receiptLineQuantity") or ln.get("quantity") or ln.get("lineQuantity") or 0))
        unit_price = ln.get("receiptLinePrice") or ln.get("linePrice") or ln.get("price")
        if unit_price is None or unit_price == 0:
            line_total_raw = ln.get("receiptLineTotal") or ln.get("lineAmount") or ln.get("amount") or 0
            unit_price = (Decimal(str(line_total_raw)) / qty) if qty else Decimal("0")
        else:
            unit_price = Decimal(str(unit_price))

        code = str(ln.get("receiptLineTaxCode") or ln.get("taxCode") or "").strip().upper()
        tax_id = ln.get("taxID")
        if tax_id is not None:
            tax_id = int(tax_id)
        if tax_id is None:
            tax_id = (
                local_to_fdms.get(code, (None, None))[0]
                or code_to_tax_id.get(code, default_tax_id)
            )
        override = local_to_fdms.get(code, (None, None))[1] if code else None
        receipt_line_tax_code = override or tax_id_to_code.get(tax_id, "") or str(tax_id)

        net_line = round2(qty * unit_price)
        subtotal_by_tax[tax_id] = subtotal_by_tax.get(tax_id, Decimal("0")) + net_line
        line_entries.append((ln, tax_id, receipt_line_tax_code, qty, unit_price, net_line))

    # Build synthetic lines (one per tax group) for FDMS tax engine: aggregate first, round once
    synthetic_lines = []
    for tax_id in sorted(subtotal_by_tax.keys()):
        if tax_id not in tax_id_to_percent:
            if strict_tax:
                raise ValueError(f"Missing tax for taxID {tax_id}. Tax must be provided; no fallback.")
            pct = 15.0
        else:
            pct = tax_id_to_percent[tax_id]
        net_band = subtotal_by_tax[tax_id]
        tax_code = (tax_id_to_code.get(tax_id) or str(tax_id))[:TAX_CODE_MAX_LENGTH] or "VAT"
        if receipt_lines_tax_inclusive and pct is not None and float(pct) > 0:
            group_total = net_band * (Decimal("1") + Decimal(str(pct)) / 100)
        else:
            group_total = net_band
        synthetic_lines.append({
            "taxID": tax_id,
            "taxCode": tax_code,
            "taxPercent": float(pct) if pct is not None else None,
            "receiptLineTotal": group_total,
        })

    receipt_taxes_units, receipt_total_float = calculate_receipt_totals(
        synthetic_lines, receipt_lines_tax_inclusive
    )

    taxes_out = []
    tax_amount_by_id = {}
    net_band_by_id = {}
    tax_code_by_id = {}
    tax_pct_by_id = {}
    for te in receipt_taxes_units:
        tax_id = te["taxID"]
        tax_amt = Decimal(str(te["taxAmount"]))
        sales_with_tax = Decimal(str(te["salesAmountWithTax"]))
        taxes_out.append({
            "taxID": tax_id,
            "taxCode": te["taxCode"],
            "taxPercent": te.get("taxPercent"),
            "taxAmount": to_cents(tax_amt),
            "salesAmountWithTax": to_cents(sales_with_tax),
        })
        tax_amount_by_id[tax_id] = tax_amt
        net_band_by_id[tax_id] = sales_with_tax - tax_amt
        tax_code_by_id[tax_id] = te["taxCode"]
        tax_pct_by_id[tax_id] = te.get("taxPercent") if te.get("taxPercent") is not None else 0.0

    receipt_total = round2(receipt_total_float)

    # Allocate to lines: proportional share of band total (no extra rounding)
    for i, (ln, tax_id, receipt_line_tax_code, qty, unit_price, net_line) in enumerate(line_entries):
        if receipt_lines_tax_inclusive:
            net_band = net_band_by_id[tax_id]
            tax_amt = tax_amount_by_id[tax_id]
            if net_band and net_band != 0:
                line_total_incl = net_line + (net_line / net_band) * tax_amt
            else:
                line_total_incl = net_line
            unit_price_for_payload = line_total_incl / qty if qty else Decimal("0")
            receipt_line_total = line_total_incl
        else:
            unit_price_for_payload = unit_price
            receipt_line_total = net_line

        ln["receiptLineNo"] = i + 1
        ln["taxID"] = tax_id
        ln["taxCode"] = tax_code_by_id[tax_id]
        ln["taxPercent"] = tax_pct_by_id[tax_id]
        ln["receiptLinePrice"] = to_cents(unit_price_for_payload)
        ln["receiptLineTotal"] = to_cents(receipt_line_total)
        ln["receiptLineQuantity"] = float(qty)
        if "receiptLineTaxCode" in ln:
            del ln["receiptLineTaxCode"]
        if "receiptLineHSCode" not in ln or not ln.get("receiptLineHSCode"):
            ln["receiptLineHSCode"] = ln.get("hs_code") or "000000"
        if "receiptLineType" not in ln or not ln.get("receiptLineType"):
            ln["receiptLineType"] = "Sale"
        lines_out.append(ln)
    return lines_out, taxes_out, receipt_total


def _validate_receipt_before_submit(
    lines_for_payload: list[dict],
    taxes_for_canonical: list[dict],
    receipt_total_cents: int,
    receipt_payments: list[dict],
    receipt_lines_tax_inclusive: bool = True,
) -> str | None:
    """
    FDMS receipt fix pack: validate before SubmitReceipt. Reject locally on mismatch.
    Returns error message or None if valid.
    """
    sum_line_cents = sum(l["receiptLineTotal"] for l in lines_for_payload)
    sum_tax_cents = sum(t["taxAmount"] for t in taxes_for_canonical)
    if receipt_lines_tax_inclusive:
        if receipt_total_cents != sum_line_cents:
            return (
                f"Receipt total mismatch (tax inclusive): receiptTotal={receipt_total_cents} != "
                f"sum(lineTotals)={sum_line_cents}"
            )
    else:
        if receipt_total_cents != sum_line_cents + sum_tax_cents:
            return (
                f"Receipt total mismatch: receiptTotal={receipt_total_cents} != "
                f"sum(lineTotals)={sum_line_cents} + sum(taxAmount)={sum_tax_cents}"
            )
    payment_total_cents = 0
    for p in receipt_payments:
        amt = p.get("paymentAmount") or p.get("amount") or 0
        payment_total_cents += to_cents(amt)
    if payment_total_cents != receipt_total_cents:
        return (
            f"Payment total ({payment_total_cents}) does not equal receipt total ({receipt_total_cents}). "
            "Adjust payment amounts to match the grand total."
        )
    if len(taxes_for_canonical) == 1:
        band = taxes_for_canonical[0]
        if band.get("salesAmountWithTax") != receipt_total_cents:
            return (
                f"Single tax band salesAmountWithTax ({band.get('salesAmountWithTax')}) "
                f"must equal receiptTotal ({receipt_total_cents})"
            )
    return None


def resolve_receipt_type(issue_tax_invoice: bool) -> str:
    """Dual-mode: FISCALINVOICE (tax invoice) or FISCALRECEIPT (retail). Never accept receiptType from UI."""
    return "FISCALINVOICE" if issue_tax_invoice else "FISCALRECEIPT"


def _build_buyer_data(customer_snapshot: dict | None) -> dict | None:
    """
    Build FDMS buyerData (BuyerDto). For FISCALINVOICE only.
    buyerAddress must be BuyerAddressDto (object with street, city, province, etc.), not a string.
    """
    if not customer_snapshot:
        return None
    name = (customer_snapshot.get("name") or "").strip()[:200] or "-"
    tin = (customer_snapshot.get("tin") or "").strip()[:10] or ""
    vat = (customer_snapshot.get("vat_number") or customer_snapshot.get("vatNumber") or "").strip()[:9] or ""
    addr_str = (customer_snapshot.get("address") or "").strip()[:100] or ""
    buyer_address = {"street": addr_str} if addr_str else {"street": ""}
    return {
        "buyerRegisterName": name,
        "buyerTIN": tin,
        "vatNumber": vat if vat else None,
        "buyerAddress": buyer_address,
    }


def submit_receipt(
    device: FiscalDevice,
    fiscal_day_no: int,
    receipt_type: str,
    receipt_currency: str,
    invoice_no: str,
    receipt_lines: list[dict],
    receipt_taxes: list[dict],
    receipt_payments: list[dict],
    receipt_total: float,
    receipt_lines_tax_inclusive: bool = True,
    receipt_date: datetime | None = None,
    original_invoice_no: str = "",
    original_receipt_global_no: int | None = None,
    progress_emit: Callable[[int, str], None] | None = None,
    customer_snapshot: dict | None = None,
    tax_from_request_only: bool = False,
    use_preallocated_credit_taxes: bool = False,
    debug_capture: dict | None = None,
    referenced_receipt: dict | None = None,
    receipt_notes: str | None = None,
) -> tuple[Receipt | None, str | None]:
    """
    Submit receipt to FDMS. Returns (Receipt, None) or (None, error_message).

    GetStatus is only run: on open day, after close day, and for/after the 1st receipt or note.
    - First receipt of the day: call GetStatus once to get lastReceiptGlobalNo; after success call GetStatus again.
    - Subsequent receipts: use device.last_receipt_global_no + 1 (no GetStatus).
    - Idempotent: if Receipt(device, fiscal_day_no, invoice_no) exists with fdms_receipt_id, return it
    - Detect duplicate receiptGlobalNo: if Receipt(device, receipt_global_no) exists, return it
    - Network failures: retried by http_client (no GetStatus on retry).
    """
    last_error = None
    for attempt in range(MAX_SUBMIT_RETRIES):
        receipt_obj, err = _do_submit_receipt(
            device=device,
            fiscal_day_no=fiscal_day_no,
            receipt_type=receipt_type,
            receipt_currency=receipt_currency,
            invoice_no=invoice_no,
            receipt_lines=receipt_lines,
            receipt_taxes=receipt_taxes,
            receipt_payments=receipt_payments,
            receipt_total=receipt_total,
            receipt_lines_tax_inclusive=receipt_lines_tax_inclusive,
            receipt_date=receipt_date,
            original_invoice_no=original_invoice_no,
            original_receipt_global_no=original_receipt_global_no,
            progress_emit=progress_emit,
            customer_snapshot=customer_snapshot or {},
            tax_from_request_only=tax_from_request_only,
            use_preallocated_credit_taxes=use_preallocated_credit_taxes,
            debug_capture=debug_capture,
            referenced_receipt=referenced_receipt,
            receipt_notes=receipt_notes,
        )
        if receipt_obj is not None:
            return receipt_obj, None
        if err is None:
            continue
        last_error = err
        err_lower = (err or "").lower()
        is_network_err = any(
            x in err_lower for x in ("connection", "timeout", "refused", "unreachable")
        )
        if attempt < MAX_SUBMIT_RETRIES - 1 and is_network_err:
            logger.warning(
                "SubmitReceipt attempt %d failed (network): %s. Retrying.",
                attempt + 1, err,
            )
            continue
        break

    err_lower = (last_error or "").lower()
    is_offline_err = any(
        x in err_lower for x in ("connection", "timeout", "refused", "unreachable", "getstatus failed")
    )
    if is_offline_err:
        try:
            from offline.services.offline_receipt import create_and_queue_offline_receipt
            receipt_obj, queue_err = create_and_queue_offline_receipt(
                device=device,
                fiscal_day_no=fiscal_day_no,
                receipt_type=receipt_type,
                receipt_currency=receipt_currency,
                invoice_no=invoice_no,
                receipt_lines=receipt_lines,
                receipt_taxes=receipt_taxes,
                receipt_payments=receipt_payments,
                receipt_total=receipt_total,
                receipt_lines_tax_inclusive=receipt_lines_tax_inclusive,
                receipt_date=receipt_date,
                original_invoice_no=original_invoice_no,
                original_receipt_global_no=original_receipt_global_no,
                customer_snapshot=customer_snapshot or {},
            )
            if receipt_obj:
                return receipt_obj, None
        except Exception as e:
            logger.exception("Offline queue failed: %s", e)

    return None, last_error


def _ensure_configs_fresh(device: FiscalDevice) -> str | None:
    """Return None if configs OK and fresh, else error message."""
    configs = get_latest_configs(device.device_id)
    if not configs:
        return "FDMS configs missing. Call GetConfig (e.g. from Device page or Re-sync) before submitting receipts."
    if not configs_are_fresh(configs):
        return "FDMS configs stale (older than 24h). Call GetConfig to refresh before submitting receipts."
    return None


def _parse_response_json(response) -> dict | None:
    """Parse response body as JSON. Returns dict or None if body is HTML or invalid JSON."""
    try:
        text = getattr(response, "text", None)
        if text is None and getattr(response, "content", None) is not None:
            text = response.content.decode("utf-8", errors="replace")
        if not text or not text.strip():
            return {}
        stripped = text.strip()
        if stripped.startswith("<"):
            return None
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None


def _response_text_preview(response, max_len: int = 500) -> str:
    """Safe preview of response text for error messages (no full HTML in logs)."""
    try:
        text = getattr(response, "text", None) or ""
        if not text:
            return ""
        if text.strip().startswith("<"):
            return "(HTML response, check FDMS URL/proxy)"
        return (text.strip()[:max_len] + "…") if len(text) > max_len else text.strip()
    except Exception:
        return ""


def _do_submit_receipt(
    device: FiscalDevice,
    fiscal_day_no: int,
    receipt_type: str,
    receipt_currency: str,
    invoice_no: str,
    receipt_lines: list[dict],
    receipt_taxes: list[dict],
    receipt_payments: list[dict],
    receipt_total: float,
    receipt_lines_tax_inclusive: bool = True,
    receipt_date: datetime | None = None,
    original_invoice_no: str = "",
    original_receipt_global_no: int | None = None,
    progress_emit: Callable[[int, str], None] | None = None,
    customer_snapshot: dict | None = None,
    tax_from_request_only: bool = False,
    use_preallocated_credit_taxes: bool = False,
    debug_capture: dict | None = None,
    referenced_receipt: dict | None = None,
    receipt_notes: str | None = None,
) -> tuple[Receipt | None, str | None]:
    """Inner submit logic. GetStatus only for first receipt of day; else use device.last_receipt_global_no."""
    if receipt_type == "CreditNote":
        logger.info("[CreditNote Submit] _do_submit_receipt entered")

    def _progress(pct: int, stage: str) -> None:
        if progress_emit:
            progress_emit(pct, stage)

    _progress(0, "Validating")
    config_err = _ensure_configs_fresh(device)
    if config_err:
        return None, config_err

    first_receipt = not Receipt.objects.filter(device=device, fiscal_day_no=fiscal_day_no).exists()
    status_data = None
    if first_receipt:
        try:
            status_data = FDMSDeviceService().get_status(device)
        except Exception as e:
            return None, f"GetStatus failed: {e}"
        fdms_last_receipt_global_no = status_data.get("lastReceiptGlobalNo")
        if fdms_last_receipt_global_no is None:
            fdms_last_receipt_global_no = 0
        receipt_global_no = int(fdms_last_receipt_global_no) + 1
    else:
        device.refresh_from_db()
        last_no = device.last_receipt_global_no
        if last_no is None:
            last_no = 0
        receipt_global_no = int(last_no) + 1
        status_data = None

    fdms_last_receipt_global_no = receipt_global_no - 1

    existing_by_global = Receipt.objects.filter(
        device=device, receipt_global_no=receipt_global_no
    ).first()
    if existing_by_global and existing_by_global.fdms_receipt_id:
        logger.info(
            "Duplicate receiptGlobalNo=%s (already submitted to FDMS), returning existing",
            receipt_global_no,
        )
        return existing_by_global, None

    if not (invoice_no and invoice_no.strip()):
        from fiscal.services.invoice_number import get_next_invoice_no
        invoice_no = get_next_invoice_no()

    if invoice_no:
        existing_by_invoice = Receipt.objects.filter(
            device=device,
            fiscal_day_no=fiscal_day_no,
            invoice_no=invoice_no,
        ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0).first()
        if existing_by_invoice:
            logger.info(
                "Idempotent: receipt (invoice_no=%s, fiscal_day=%s) already submitted, returning existing",
                invoice_no, fiscal_day_no,
            )
            return existing_by_invoice, None

    status = status_data.get("fiscalDayStatus") if status_data else device.fiscal_day_status
    if status not in ("FiscalDayOpened", "FiscalDayCloseFailed"):
        return None, f"Cannot submit: status must be FiscalDayOpened or FiscalDayCloseFailed (current: {status})"

    if not receipt_lines or not receipt_taxes or not receipt_payments:
        return None, "receiptLines, receiptTaxes, receiptPayments required"
#user edit
    for i, ln in enumerate(receipt_lines):
        hs = (ln.get("receiptLineHSCode") or ln.get("hs_code") or "1122").strip()
        if not hs:
            return None, (
                f"Line {i + 1}: HS code is required. "
                "Provide receiptLineHSCode or hs_code for every line."
            )
        if len(hs) not in (4, 8):
            return None, (
                f"Line {i + 1}: HS code must be 4 or 8 characters (got {len(hs)}). "
                f"Value: {hs!r}"
            )

    if receipt_type == "CreditNote":
        err = _validate_credit_note(device, original_invoice_no or "", original_receipt_global_no)
        if err:
            return None, err
        # Always negate amounts for credit note so callers can send positive values
        receipt_lines, receipt_taxes, receipt_payments, receipt_total = _transform_to_credit_note(
            receipt_lines, receipt_taxes, receipt_payments, receipt_total
        )
        # FDMS requirement: receiptTaxes.taxAmount, salesAmountWithTax and paymentAmount must not be positive (negative or zero)
        for t in receipt_taxes or []:
            tax_amt = t.get("taxAmount")
            if tax_amt is not None and float(tax_amt) > 0:
                return None, "Credit note: receiptTaxes.taxAmount must be negative."
            sales = t.get("salesAmountWithTax")
            if sales is not None and float(sales) > 0:
                return None, "Credit note: receiptTaxes.salesAmountWithTax must be negative."
        for p in receipt_payments or []:
            amt = p.get("paymentAmount") or p.get("amount")
            if amt is not None and float(amt) > 0:
                return None, "Credit note: paymentAmount must be negative."
    if receipt_type == "DebitNote" and referenced_receipt is None:
        return None, "Debit note requires creditDebitNote reference (RCPT015)."

    configs = get_latest_configs(device.device_id)
    if configs and not tax_from_request_only:
        try:
            validate_against_configs(
                receipt_currency=receipt_currency,
                receipt_taxes=receipt_taxes,
                receipt_lines=receipt_lines,
                configs=configs,
            )
        except ValidationError as e:
            return None, str(e)

    if not device.is_vat_registered:
        for tax in receipt_taxes or []:
            pct = tax.get("taxPercent") or tax.get("fiscalCounterTaxPercent") or 0
            if float(pct) > 0:
                return None, (
                    "VAT tax used while taxpayer is not VAT registered. "
                    "Device must be verified as VAT registered before using VAT."
                )

    _progress(20, "Building canonical")
    receipt_date = receipt_date or datetime.now()
    receipt_date_str = receipt_date.strftime("%Y-%m-%dT%H:%M:%S")

    last_receipt = Receipt.objects.filter(
        device=device, fiscal_day_no=fiscal_day_no
    ).order_by("-receipt_counter").first()

    if last_receipt:
        receipt_counter = last_receipt.receipt_counter + 1
        previous_receipt_hash = last_receipt.receipt_hash or None
        if last_receipt.receipt_global_no != fdms_last_receipt_global_no:
            return None, (
                f"Local receipt chain out of sync with FDMS: "
                f"lastReceiptGlobalNo={fdms_last_receipt_global_no} but local last receipt_global_no={last_receipt.receipt_global_no}. "
                f"Re-sync required before submitting."
            )
    else:
        receipt_counter = 1
        previous_receipt_hash = None

    if tax_from_request_only:
        # taxID 1 -> "1", 2 -> "2", 517 -> "517" (FDMS payload)
        TAX_ID_TO_CODE = {1: "1", 2: "2", 517: "517"}
        tax_id_to_code = {}
        tax_id_to_percent = {}
        for t in receipt_taxes or []:
            tid = t.get("taxID")
            if tid is None:
                return None, "receipt_taxes must include taxID for each tax band when tax_from_request_only."
            tid_int = int(tid)
            pct = t.get("taxPercent") if t.get("taxPercent") is not None else t.get("fiscalCounterTaxPercent")
            if pct is None:
                return None, f"receipt_taxes must include taxPercent for taxID {tid_int}. No fallback."
            tax_id_to_percent[tid_int] = round(float(pct), 2)
            tax_id_to_code[tid_int] = TAX_ID_TO_CODE.get(tid_int, str(tid_int))
        local_to_fdms = {}
        taxes_enriched = list(receipt_taxes)
        code_to_tax_id = {str(t.get("taxCode", "") or "").strip().upper(): int(t.get("taxID")) for t in receipt_taxes if t.get("taxID") is not None}
        default_tax_id = next((int(t.get("taxID")) for t in receipt_taxes if t.get("taxID") is not None), 1)
        strict_tax = True
    else:
        tax_id_to_code = dict(get_tax_id_to_code(configs))
        tax_id_to_percent = dict(get_tax_id_to_percent(configs))
        for t in receipt_taxes or []:
            tid = t.get("taxID")
            if tid is None:
                continue
            tid_int = int(tid)
            pct = t.get("taxPercent") if t.get("taxPercent") is not None else t.get("fiscalCounterTaxPercent")
            if pct is not None:
                tax_id_to_percent[tid_int] = round(float(pct), 2)
            code = (str(t.get("taxCode") or "").strip()[:TAX_CODE_MAX_LENGTH]) or None
            if code:
                tax_id_to_code[tid_int] = code
        local_to_fdms = get_local_code_to_fdms_tax(configs)
        taxes_enriched = enrich_receipt_taxes_with_tax_id(configs, receipt_taxes)
        code_to_tax_id = {str(t.get("taxCode", "") or "").strip().upper(): t.get("taxID", 1) for t in taxes_enriched if t.get("taxID") is not None}
        default_tax_id = next((t.get("taxID") for t in taxes_enriched if t.get("taxID") is not None), 1)
        strict_tax = False

    # For credit notes: fetch original invoice so exempt/zero-rated lines can use its 8-digit HS code (FDMS requirement)
    applicable_taxes = get_tax_table_from_configs(configs) if configs else []
    exempt_tax_ids = get_exempt_tax_ids(applicable_taxes) if applicable_taxes else set()
    original_receipt = None
    if receipt_type == "CreditNote" and original_receipt_global_no is not None:
        original_receipt = Receipt.objects.filter(
            device=device, receipt_global_no=original_receipt_global_no
        ).first()

    if use_preallocated_credit_taxes and receipt_type == "CreditNote":
        lines_for_payload = []
        for i, ln in enumerate(receipt_lines):
            total_val = Decimal(str(ln.get("receiptLineTotal") or ln.get("lineAmount") or 0))
            qty = Decimal(str(ln.get("receiptLineQuantity") or ln.get("quantity") or 1))
            unit_price = total_val / qty if qty else Decimal("0")
            hs = str(ln.get("receiptLineHSCode") or ln.get("hs_code") or "0000").strip()[:8]
            # Exempt/zero-rated lines must have 8-digit HS: use original invoice line HS when available
            if original_receipt and original_receipt.receipt_lines and i < len(original_receipt.receipt_lines):
                tid = ln.get("taxID", 1)
                pct = ln.get("taxPercent")
                is_exempt_zero = tid is not None and (
                    int(tid) in exempt_tax_ids or (pct is not None and float(pct) == 0)
                )
                if is_exempt_zero:
                    orig_ln = original_receipt.receipt_lines[i]
                    orig_hs = str(orig_ln.get("receiptLineHSCode") or orig_ln.get("hs_code") or "").strip()
                    orig_digits = "".join(c for c in orig_hs if c.isdigit())
                    if len(orig_digits) == 8:
                        hs = orig_hs
                    elif len(orig_digits) == 4:
                        # Original has 4-digit; pad to 8 so FDMS accepts exempt/zero-rated line
                        hs = orig_digits + "0000"
            lines_for_payload.append({
                "receiptLineNo": i + 1,
                "receiptLineQuantity": float(qty),
                "receiptLineTotal": to_cents(total_val),
                "receiptLinePrice": to_cents(unit_price),
                "receiptLineName": str(ln.get("receiptLineName") or "Credit")[:200],
                "receiptLineHSCode": hs[:8],
                "receiptLineType": ln.get("receiptLineType") or "Sale",
                "taxID": ln.get("taxID", 1),
                "taxCode": str(ln.get("taxCode") or "1")[:TAX_CODE_MAX_LENGTH],
                "taxPercent": round(float(ln.get("taxPercent", 0)), 2),
            })
        taxes_for_canonical = []
        for t in receipt_taxes or []:
            tax_amt = Decimal(str(t.get("taxAmount") or 0))
            sales_amt = Decimal(str(t.get("salesAmountWithTax") or 0))
            taxes_for_canonical.append({
                "taxID": t.get("taxID", 1),
                "taxCode": str(t.get("taxCode") or "1")[:TAX_CODE_MAX_LENGTH],
                "taxPercent": round(float(t.get("taxPercent") or 0), 2),
                "taxAmount": to_cents(tax_amt),
                "salesAmountWithTax": to_cents(sales_amt),
            })
        receipt_total_recalc = Decimal(str(receipt_total))
    else:
        try:
            lines_for_payload, taxes_for_canonical, receipt_total_recalc = _recalculate_receipt_server_side(
                receipt_lines=receipt_lines,
                configs=configs,
                receipt_lines_tax_inclusive=receipt_lines_tax_inclusive,
                local_to_fdms=local_to_fdms,
                code_to_tax_id=code_to_tax_id,
                default_tax_id=default_tax_id,
                tax_id_to_code=tax_id_to_code,
                tax_id_to_percent=tax_id_to_percent,
                strict_tax=strict_tax,
            )
        except ValueError as e:
            return None, str(e)

    receipt_total = receipt_total_recalc
    receipt_total_cents = to_cents(receipt_total)
    sum_line_totals_cents = sum(l["receiptLineTotal"] for l in lines_for_payload)
    sum_tax_amount_cents = sum(t["taxAmount"] for t in taxes_for_canonical)
    if receipt_lines_tax_inclusive:
        if receipt_total_cents != sum_line_totals_cents and receipt_type!="CreditNote":
            return None, (
                f"Internal error: receiptTotal ({receipt_total_cents}) != sum(lineTotals) ({sum_line_totals_cents})"
            )
    else:
        if receipt_total_cents != sum_line_totals_cents + sum_tax_amount_cents and receipt_type!="CreditNote":
            return None, (
                f"Internal error: receiptTotal ({receipt_total_cents}) != subtotal ({sum_line_totals_cents}) + tax ({sum_tax_amount_cents})"
            )

    err = _validate_receipt_before_submit(
        lines_for_payload, taxes_for_canonical, receipt_total_cents, receipt_payments,
        receipt_lines_tax_inclusive=receipt_lines_tax_inclusive,
    )
    if err:
        return None, err

    # Strict tax mapping: validate tax combination and HS code before submit (when FDMS config available)
    # applicable_taxes and exempt_tax_ids already set above for credit-note HS handling
    # Credit note: for exempt/zero-rated lines with 4-digit HS, use original invoice HS code (must be 8 digits)
    if receipt_type == "CreditNote" and original_receipt and original_receipt.receipt_lines:
        original_lines = original_receipt.receipt_lines
        for i, ln in enumerate(lines_for_payload):
            if i >= len(original_lines):
                break
            tid = ln.get("taxID")
            pct = ln.get("taxPercent")
            is_exempt_zero = tid is not None and (
                int(tid) in exempt_tax_ids or (pct is not None and float(pct) == 0)
            )
            if not is_exempt_zero:
                continue
            hs = str(ln.get("receiptLineHSCode") or ln.get("hs_code") or "").strip()
            digits = "".join(c for c in hs if c.isdigit())
            if len(digits) != 8 and len(digits) == 4:
                orig_ln = original_lines[i]
                orig_hs = str(orig_ln.get("receiptLineHSCode") or orig_ln.get("hs_code") or "").strip()
                orig_digits = "".join(c for c in orig_hs if c.isdigit())
                if len(orig_digits) == 8:
                    ln["receiptLineHSCode"] = orig_hs
                    ln["hs_code"] = orig_hs
                elif len(orig_digits) == 4:
                    # Original has 4-digit; pad to 8 so FDMS accepts exempt/zero-rated line
                    ln["receiptLineHSCode"] = orig_digits + "0000"
                    ln["hs_code"] = orig_digits + "0000"
    if applicable_taxes:
        try:
            for t in taxes_for_canonical:
                tid = t.get("taxID")
                if tid is None:
                    continue
                pct = None if int(tid) in exempt_tax_ids else t.get("taxPercent")
                validate_tax_combination(applicable_taxes, int(tid), pct)
            for ln in lines_for_payload:
                validate_hs_code_for_vat_taxpayer(
                    ln, ln.get("taxID"), ln.get("taxPercent"), exempt_tax_ids
                )
        except ValidationError as e:
            return None, str(e)

    # Credit note: FDMS requires receiptTaxes (taxAmount, salesAmountWithTax), paymentAmount, line totals negative in payload.
    # Normalize BEFORE canonical so canonical and payload match.
    if receipt_type == "CreditNote":
        for t in taxes_for_canonical:
            if "taxAmount" in t and t["taxAmount"] > 0:
                t["taxAmount"] = -abs(t["taxAmount"])
            if "salesAmountWithTax" in t and t["salesAmountWithTax"] > 0:
                t["salesAmountWithTax"] = -abs(t["salesAmountWithTax"])
        for ln in lines_for_payload:
            for k in ("receiptLineTotal", "receiptLinePrice"):
                if k in ln and ln[k] > 0:
                    ln[k] = -abs(ln[k])
        if receipt_total_cents > 0:
            receipt_total_cents = -abs(receipt_total_cents)
        receipt_total_recalc = -abs(receipt_total_recalc) if receipt_total_recalc > 0 else receipt_total_recalc
        for p in receipt_payments:
            amt = p.get("paymentAmount") or p.get("amount")
            if amt is not None and float(amt) > 0:
                p["paymentAmount"] = -abs(float(amt))
                if "amount" in p:
                    p["amount"] = p["paymentAmount"]

    # First receipt of day: do not include previousReceiptHash in canonical. Later receipts: must include.
    # Canonical builder expects tax amounts as decimals; Exempt must have no taxPercent key (FDMS RCPT020).
    taxes_for_canonical_decimal = []
    for t in taxes_for_canonical:
        t_copy = {k: v for k, v in t.items() if k not in ("taxAmount", "salesAmountWithTax")}
        if t_copy.get("taxID") in exempt_tax_ids:
            t_copy.pop("taxPercent", None)
        taxes_for_canonical_decimal.append({
            **t_copy,
            "taxAmount": Decimal(t["taxAmount"]) / 100,
            "salesAmountWithTax": Decimal(t["salesAmountWithTax"]) / 100,
        })
    canonical = build_receipt_canonical_string(
        device_id=device.device_id,
        receipt_type=receipt_type,
        receipt_currency=receipt_currency,
        receipt_global_no=receipt_global_no,
        receipt_date=receipt_date_str,
        receipt_total=receipt_total_recalc,
        receipt_tax_lines=taxes_for_canonical_decimal,
        previous_receipt_hash=previous_receipt_hash,
    )
    logger.info("[SubmitReceipt] CANONICAL STRING (signed before submit) receiptType=%s receiptGlobalNo=%s: [REDACTED]", receipt_type, receipt_global_no)
    logger.debug("[SubmitReceipt] CANONICAL STRING (being hashed): [REDACTED]")

    _progress(40, "Signing")
    sig = sign_receipt(device, canonical)

    payments_for_payload = []
    for p in receipt_payments:
        amt = Decimal(str(p.get("paymentAmount") or p.get("amount") or 0))
        method = str(p.get("moneyType") or p.get("method") or "CASH").strip().upper()
        money_type_code = _MONEY_TYPE_MAP.get(method, "Other")
        payments_for_payload.append({
            "moneyTypeCode": money_type_code,
            "paymentAmount": to_cents(amt),
        })

    # FDMS fix pack: each line must have taxCode, taxPercent, taxID; must NOT have receiptLineTaxCode
    # Exempt: omit taxPercent from payload (never send taxPercent 0.0 for Exempt). Zero-rated: include taxPercent.
    receipt_lines_for_payload = []
    for ln in lines_for_payload:
        line_copy = {k: v for k, v in ln.items() if k != "receiptLineTaxCode"}
        if line_copy.get("taxID") in exempt_tax_ids:
            line_copy.pop("taxPercent", None)
        receipt_lines_for_payload.append(line_copy)
    receipt_taxes_for_payload = []
    for t in taxes_for_canonical:
        t_copy = dict(t)
        if t_copy.get("taxID") in exempt_tax_ids:
            t_copy.pop("taxPercent", None)
            if t_copy.get("taxAmount") != 0:
                t_copy["taxAmount"] = 0
        receipt_taxes_for_payload.append(t_copy)
    receipt_type_upper = str(receipt_type).strip().upper() if receipt_type else "FISCALINVOICE"
    receipt_dto = {
        "deviceID": device.device_id,
        "receiptType": receipt_type_upper,
        "receiptCurrency": receipt_currency,
        "receiptGlobalNo": receipt_global_no,
        "receiptCounter": receipt_counter,
        "invoiceNo": (invoice_no or "")[:50],
        "receiptDate": receipt_date_str,
        "receiptTotal": receipt_total_cents,
        "receiptLinesTaxInclusive": bool(receipt_lines_tax_inclusive),
        "receiptLines": receipt_lines_for_payload,
        "receiptTaxes": receipt_taxes_for_payload,
        "receiptPayments": payments_for_payload,
        "receiptDeviceSignature": {
            "hash": sig["hash"],
            "signature": sig["signature"],
        },
    }
    if previous_receipt_hash:
        receipt_dto["previousReceiptHash"] = previous_receipt_hash
    if receipt_type in ("CreditNote", "DebitNote") and referenced_receipt is not None:
        receipt_dto["creditDebitNote"] = referenced_receipt
    if receipt_type in ("CreditNote", "DebitNote") and receipt_notes is not None:
        receipt_dto["receiptNotes"] = receipt_notes
    # buyerData block omitted from payload

    _progress(60, "Sending to FDMS")
    path = f"/Device/v1/{device.device_id}/SubmitReceipt"
    payload = {"receipt": receipt_dto}
    body = _fdms_json_dumps(payload)
    if debug_capture is not None:
        debug_capture["request"] = body
    body_for_log = _fdms_json_dumps(mask_sensitive_fields(copy.deepcopy(payload)))
    logger.info("[SubmitReceipt] REQUEST POST %s receiptType=%s receiptGlobalNo=%s\n%s", path, receipt_type, receipt_global_no, body_for_log)
    logger.debug("[SubmitReceipt] REQUEST POST %s payload:\n%s", path, body_for_log)
    service = FDMSDeviceService()
    try:
        response = service.device_request("POST", path, body=body, device=device)
        resp_body = _parse_response_json(response)
        if isinstance(resp_body, dict):
            resp_log = json.dumps(mask_sensitive_fields(resp_body), indent=2, default=str)
        else:
            resp_log = redact_string_for_log(response.text or "(empty)")
        logger.info("[SubmitReceipt] RESPONSE status=%s receiptType=%s receiptGlobalNo=%s\n%s", response.status_code, receipt_type, receipt_global_no, resp_log)
        logger.debug("[SubmitReceipt] RESPONSE status=%s body:\n%s", response.status_code, resp_log)
        if debug_capture is not None:
            debug_capture["response_status"] = response.status_code
            debug_capture["response"] = resp_log
    except Exception as e:
        logger.exception("SubmitReceipt failed")
        return None, str(e)

    if response.status_code != 200:
        try:
            from fiscal.services.receipt_submission_response_service import store_receipt_submission_response
            store_receipt_submission_response(
                device=device,
                receipt_global_no=receipt_global_no,
                status_code=response.status_code,
                response_body=resp_body if isinstance(resp_body, dict) else {"text": _response_text_preview(response)},
                fiscal_day_no=fiscal_day_no,
                receipt=None,
            )
        except Exception as e:
            logger.warning("Store submission response failed: %s", e)
        err_body = resp_body if isinstance(resp_body, dict) else {}
        detail = err_body.get("detail", err_body.get("title")) or _response_text_preview(response) or f"HTTP {response.status_code}"
        return None, detail

    _progress(80, "Verifying")
    data = resp_body if isinstance(resp_body, dict) else None
    if data is None:
        return None, (
            "FDMS returned non-JSON (e.g. HTML error page). "
            "Check FDMS URL, proxy, and network. Response: " + _response_text_preview(response)
        )
    server_sig = data.get("receiptServerSignature") or {}
    fdms_receipt_id = data.get("receiptID")
    operation_id = (data.get("operationID") or data.get("operationId") or "").strip()[:120]
    server_date_parsed = None
    for key in ("serverDate", "server_date"):
        raw = data.get(key) or (server_sig.get(key) if isinstance(server_sig, dict) else None)
        if raw:
            try:
                s = str(raw).strip().replace("Z", "+00:00")
                server_date_parsed = datetime.fromisoformat(s)
            except Exception:
                try:
                    server_date_parsed = datetime.strptime(str(raw)[:19], "%Y-%m-%dT%H:%M:%S")
                except Exception:
                    pass
            break

    lines_for_storage = [
        {
            **{k: v for k, v in ln.items() if k not in ("receiptLinePrice", "receiptLineTotal")},
            "receiptLinePrice": float(Decimal(ln["receiptLinePrice"]) / 100),
            "receiptLineTotal": float(Decimal(ln["receiptLineTotal"]) / 100),
        }
        for ln in lines_for_payload
    ]
    taxes_for_storage = [
        {
            **{k: v for k, v in t.items() if k not in ("taxAmount", "salesAmountWithTax")},
            "taxAmount": float(Decimal(t["taxAmount"]) / 100),
            "salesAmountWithTax": float(Decimal(t["salesAmountWithTax"]) / 100),
        }
        for t in taxes_for_canonical
    ]
    payments_for_storage = [
        {**p, "paymentAmount": float(Decimal(p["paymentAmount"]) / 100)}
        for p in payments_for_payload
    ]

    receipt_total_dec = Decimal(str(receipt_total))
    is_invoice = (receipt_type or "").strip().upper() in ("FISCALINVOICE",)
    defaults = {
        "fiscal_day_no": fiscal_day_no,
        "receipt_counter": receipt_counter,
        "currency": receipt_currency,
        "receipt_taxes": taxes_for_storage,
        "receipt_lines": lines_for_storage,
        "receipt_payments": payments_for_storage,
        "receipt_lines_tax_inclusive": receipt_lines_tax_inclusive,
        "receipt_type": receipt_type,
        "invoice_no": invoice_no,
        "original_invoice_no": (original_invoice_no or "").strip(),
        "original_receipt_global_no": original_receipt_global_no,
        "receipt_date": receipt_date,
        "receipt_total": receipt_total_dec,
        "canonical_string": canonical,
        "receipt_hash": sig["hash"],
        "receipt_signature_hash": sig["hash"],
        "receipt_signature_sig": sig["signature"],
        "receipt_server_signature": server_sig,
        "fdms_receipt_id": fdms_receipt_id,
        "customer_snapshot": customer_snapshot or {},
        "operation_id": operation_id,
        "server_date": server_date_parsed,
    }
    tenant_id = getattr(device, "tenant_id", None)
    if tenant_id is None:
        from tenants.utils import get_default_tenant
        default_tenant = get_default_tenant()
        if default_tenant is not None:
            tenant_id = default_tenant.pk
    if tenant_id is not None:
        defaults["tenant_id"] = tenant_id
    if is_invoice:
        defaults["original_total"] = receipt_total_dec
        defaults["document_type"] = "INVOICE"

    with transaction.atomic():
        device = FiscalDevice.objects.select_for_update().get(pk=device.pk)
        receipt_obj, created = Receipt.objects.update_or_create(
            device=device,
            receipt_global_no=receipt_global_no,
            defaults=defaults,
        )
        if not created:
            logger.info(
                "Duplicate receipt_global_no=%s: FDMS returned 200 (idempotent), updated existing",
                receipt_global_no,
            )
        device.last_receipt_global_no = receipt_global_no
        device.save(update_fields=["last_receipt_global_no"])
        # ZIMRA Section 10: map FDMS response to fiscal_invoice_number, receipt_number,
        # fiscal_signature, verification_code, VAT breakdown, buyer (before marking final)
        try:
            from fiscal.services.fdms_response_mapper import apply_fdms_response_to_receipt
            apply_fdms_response_to_receipt(receipt_obj, data)
        except Exception as e:
            logger.warning("FDMS response mapper failed for receipt %s: %s", receipt_global_no, e)

    if first_receipt:
        try:
            FDMSDeviceService().get_status(device)
        except Exception as e:
            logger.warning("GetStatus after first receipt (non-fatal): %s", e)

    try:
        from fiscal.services.receipt_submission_response_service import store_receipt_submission_response
        store_receipt_submission_response(
            device=device,
            receipt_global_no=receipt_global_no,
            status_code=200,
            response_body=data,
            fiscal_day_no=fiscal_day_no,
            receipt=receipt_obj,
        )
    except Exception as e:
        logger.warning("Store submission response failed: %s", e)

    _progress(100, "Completed")
    logger.info("SubmitReceipt OK: device=%s receiptGlobalNo=%s receiptID=%s",
                device.device_id, receipt_global_no, fdms_receipt_id)
    try:
        from fiscal.services.qr_service import attach_qr_to_receipt
        receipt_obj.refresh_from_db()  # ensure receipt_hash and receipt_type are loaded before QR
        attach_qr_to_receipt(receipt_obj)
    except Exception as e:
        logger.warning("QR attach failed for receipt %s: %s", receipt_global_no, e)

    _persist_invoice_pdf_if_enabled(receipt_obj, receipt_global_no)

    return receipt_obj, None
