"""
ZIMRA FDMS API v7.2 – InvoiceA4 PDF generator.
Section 10 (InvoiceA4 View), Section 11 (QR Code), Section 13 (Signature Rules).
Uses WeasyPrint for HTML→PDF when available; falls back to xhtml2pdf on Windows
(where WeasyPrint requires GTK/Cairo). Validates mandatory fields and total reconciliation.
"""

import logging
import re
from io import BytesIO
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string

logger = logging.getLogger("fiscal")


def _strip_weasyprint_only_css(html: str) -> str:
    """
    Remove @page margin boxes (@bottom-right, counter(page), etc.) that xhtml2pdf
    does not support and returns NotImplemented for, causing 'NotImplementedType' object is not iterable.
    Keeps a simple @page { size: A4; margin: 12mm; } so xhtml2pdf can parse the stylesheet.
    """
    # Remove @bottom-right { ... } block (and any similar margin box)
    html = re.sub(
        r"@bottom-right\s*\{[^}]*\}",
        "",
        html,
        flags=re.DOTALL,
    )
    # Remove @top-left, @top-right, @bottom-left, @bottom-center, @top-center if present
    for at in ("@top-left", "@top-right", "@bottom-left", "@bottom-center", "@top-center"):
        html = re.sub(rf"{re.escape(at)}\s*\{{[^}}]*\}}", "", html, flags=re.DOTALL)
    return html


def _html_to_pdf(html: str) -> bytes:
    """
    Convert HTML string to PDF bytes. Tries WeasyPrint first, then xhtml2pdf.
    WeasyPrint often fails on Windows (missing GTK/Cairo libs); xhtml2pdf is pure Python and used as fallback.
    xhtml2pdf does not support @page margin boxes (e.g. @bottom-right, counter(page)); we strip them for the fallback.
    """
    # 1. WeasyPrint (best CSS support; requires system libs on Windows)
    try:
        from weasyprint import HTML
        return HTML(string=html, base_url=None).write_pdf()
    except Exception as e:
        logger.info("WeasyPrint unavailable (%s), using xhtml2pdf fallback", e)
    # 2. xhtml2pdf (pure Python, no system libs; works on Windows)
    try:
        from xhtml2pdf import pisa
        html_safe = _strip_weasyprint_only_css(html)
        dest = BytesIO()
        pisa_status = pisa.CreatePDF(html_safe, dest=dest, encoding="utf-8")
        if pisa_status.err:
            raise ValidationError("xhtml2pdf failed to generate PDF")
        return dest.getvalue()
    except ImportError:
        raise ValidationError(
            "PDF generation failed (WeasyPrint needs extra libraries on this system). "
            "Install xhtml2pdf for a fallback: pip install xhtml2pdf"
        )


def _validate_receipt_for_invoice_a4(receipt) -> None:
    """
    Enforce all mandatory Section 10 fiscal fields and total reconciliation.
    VAT registered: HS Code required (4 or 8 digits) per line. Raises ValidationError if invalid.
    """
    if not receipt.fdms_receipt_id:
        raise ValidationError("Mandatory fiscal field missing: receipt_id (fdms_receipt_id). Receipt must be fiscalised.")
    if receipt.fiscal_day_no is None:
        raise ValidationError("Mandatory fiscal field missing: fiscal_day_no.")
    if receipt.receipt_counter is None:
        raise ValidationError("Mandatory fiscal field missing: receipt_counter.")
    if not receipt.receipt_type:
        raise ValidationError("Mandatory fiscal field missing: receipt_type.")
    if not receipt.receipt_date and not getattr(receipt, "created_at", None):
        raise ValidationError("Mandatory fiscal field missing: receipt_date.")
    if not getattr(receipt, "device", None):
        raise ValidationError("Mandatory fiscal field missing: device_id (device).")
    device = receipt.device
    if device:
        if not (getattr(device, "taxpayer_name", None) or getattr(device, "taxpayer_tin", None)):
            from fiscal.services.config_service import get_latest_configs
            configs = get_latest_configs(device.device_id)
            raw = configs.raw_response if configs else {}
            if not raw.get("taxPayerName") and not raw.get("taxpayerName") and not raw.get("taxPayerTIN"):
                raise ValidationError("Mandatory fiscal field missing: taxpayer name or TIN.")
        if not (receipt.receipt_hash or "").strip():
            raise ValidationError("Mandatory fiscal field missing: device signature (receipt_hash).")
        if not receipt.receipt_server_signature:
            raise ValidationError("Mandatory fiscal field missing: FDMS signature (receipt_server_signature).")

    receipt_lines = receipt.receipt_lines if isinstance(receipt.receipt_lines, list) else []
    receipt_taxes = receipt.receipt_taxes if isinstance(getattr(receipt, "receipt_taxes", None), list) else []
    if not receipt_lines:
        raise ValidationError("Receipt has no line items.")

    # Totals must reconcile exactly with receiptTotal
    subtotal = Decimal("0")
    for line in receipt_lines:
        amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
        subtotal += Decimal(str(amt))
    total_tax = sum(Decimal(str(t.get("taxAmount") or 0)) for t in receipt_taxes)
    expected_total = subtotal + total_tax
    rec_total = Decimal(str(receipt.receipt_total or 0))
    if abs(expected_total - rec_total) > Decimal("0.01"):
        raise ValidationError(
            f"Totals must reconcile with receiptTotal: subtotal + tax = {expected_total}, receiptTotal = {rec_total}."
        )

    if not (receipt_taxes and (receipt.receipt_payments if isinstance(receipt.receipt_payments, list) else [])):
        raise ValidationError("Receipt must have receiptTaxes and receiptPayments.")

    # VAT registered: HS Code required (4 or 8 digits) per line
    if device and getattr(device, "is_vat_registered", False):
        for i, line in enumerate(receipt_lines):
            hs = (line.get("receiptLineHSCode") or line.get("hs_code") or "").strip()
            digits = "".join(c for c in hs if c.isdigit())
            if len(digits) not in (4, 8):
                raise ValidationError(
                    f"Line {i + 1}: HS Code must be 4 or 8 digits for VAT registered taxpayer (FDMS). Got: {hs!r}"
                )


def generate_fiscal_invoice_pdf(receipt) -> bytes:
    """
    Generate 100% ZIMRA-compliant InvoiceA4 PDF for a fiscalised receipt.

    - Renders templates/invoices/fiscal_invoice_a4.html (Tax Invoice) with context from build_fiscal_invoice_a4_context.
    - Generates QR code (Section 11) from qrUrl + receiptDeviceSignature hash, embeds as base64 image.
    - Returns PDF bytes. Saves to media/fiscal_invoices/{receiptID}.pdf when called from receipt_service.

    Compliance mapping:
      Section 10: Header (taxpayer, TIN, VAT, branch, device serial/ID), Fiscal block (receiptID, fiscalDayNo,
                  receiptCounter, receiptGlobalNo, invoiceNo, receiptType, receiptDate, receiptCurrency,
                  operationID, serverDate), Buyer (if buyerData), Line items (HS Code, tax %), Tax summary,
                  Totals, Payment, Signatures.
      Section 11: QR = qrUrl + receiptDeviceSignature.hash (we use full verification URL).
      Section 13: receiptDeviceSignature.hash, receiptServerSignature.signature.

    Raises ValidationError if required fields missing or totals do not reconcile.
    """
    from fiscal.services.fiscal_invoice_context import get_receipt_print_template_and_context

    _validate_receipt_for_invoice_a4(receipt)
    template_name, ctx = get_receipt_print_template_and_context(receipt)
    html = render_to_string(template_name, ctx)
    return _html_to_pdf(html)


def generate_fiscal_invoice_a4_pdf_section10(receipt) -> bytes:
    """
    Generate Section 10 compliant A4 PDF: Tax Invoice or Fiscal Credit Note.
    Runs Section 10 validation first. Uses VAT breakdown and buyer fields.
    QR encodes ZIMRA verification URL.
    Raises ValidationError if validation fails. Do NOT generate PDF on validation failure.
    """
    from fiscal.services.section10_validation import validate_receipt_for_section10_pdf
    from fiscal.services.fiscal_invoice_context import get_receipt_print_template_and_context

    validate_receipt_for_section10_pdf(receipt)
    template_name, ctx = get_receipt_print_template_and_context(receipt)
    html = render_to_string(template_name, ctx)
    return _html_to_pdf(html)


def generate_fiscal_invoice_pdf_from_template(receipt) -> bytes:
    """
    Generate A4 PDF from the exact same template and context as the print view.
    So the PDF is a copy of what is shown on print (same HTML rendered to PDF).
    Uses WeasyPrint when available, else xhtml2pdf (Windows-friendly).
    """
    from fiscal.services.fiscal_invoice_context import get_receipt_print_template_and_context

    template_name, ctx = get_receipt_print_template_and_context(receipt)
    html = render_to_string(template_name, ctx)
    return _html_to_pdf(html)
