"""
Strict tax mapping for FDMS. Prevents RCPT025 by mapping frontend tax to correct taxID
and enforcing Exempt / Zero Rated / Standard VAT rules.
"""

from django.core.exceptions import ValidationError


def _get_applicable_taxes_list(applicable_taxes):
    """Normalize applicable_taxes to a list of dicts."""
    if not applicable_taxes:
        return []
    if isinstance(applicable_taxes, list):
        return applicable_taxes
    return list(applicable_taxes)


def get_exempt_tax_ids(applicable_taxes):
    """
    Return set of taxIDs that are Exempt (taxName Exempt or taxPercent None in FDMS).
    Used when building payload to omit taxPercent for these IDs.
    """
    taxes = _get_applicable_taxes_list(applicable_taxes)
    exempt_ids = set()
    for t in taxes:
        tid = t.get("taxID")
        if tid is None:
            continue
        name = (t.get("taxName") or "").strip().lower()
        pct = t.get("taxPercent") if t.get("taxPercent") is not None else t.get("fiscalCounterTaxPercent")
        if name == "exempt" or pct is None:
            exempt_ids.add(int(tid))
    return exempt_ids


def is_exempt_tax_id(applicable_taxes, tax_id):
    """True if tax_id is Exempt per FDMS config."""
    return int(tax_id) in get_exempt_tax_ids(applicable_taxes)


def map_tax_from_percent(applicable_taxes, tax_percent, is_exempt=False):
    """
    Maps frontend taxPercent to correct FDMS taxID.
    Returns dict with taxID, taxCode, and taxPercent (None for Exempt).
    """
    taxes = _get_applicable_taxes_list(applicable_taxes)
    if not taxes:
        raise ValidationError("No FDMS taxes configured")

    if is_exempt:
        tax = next((t for t in taxes if (t.get("taxName") or "").lower() == "exempt"), None)
        if not tax:
            raise ValidationError("Exempt tax not configured in FDMS")
        return {
            "taxID": tax["taxID"],
            "taxCode": str(tax["taxID"]),
            "taxPercent": None,
        }

    tax = next((t for t in taxes if t.get("taxPercent") == tax_percent), None)
    if not tax:
        raise ValidationError(f"No FDMS tax configured for percent {tax_percent}")

    return {
        "taxID": tax["taxID"],
        "taxCode": str(tax["taxID"]),
        "taxPercent": tax_percent,
    }


def validate_tax_combination(applicable_taxes, tax_id, tax_percent):
    """
    Validate that (tax_id, tax_percent) matches FDMS configuration.
    Exempt must not include taxPercent; other taxes must match configured percent.
    """
    taxes = _get_applicable_taxes_list(applicable_taxes)
    tax = next((t for t in taxes if t.get("taxID") == tax_id), None)

    if not tax:
        raise ValidationError("Invalid taxID")

    if tax.get("taxPercent") is None:
        # Exempt
        if tax_percent is not None:
            raise ValidationError("Exempt tax must not include taxPercent")
    else:
        if tax.get("taxPercent") != tax_percent:
            raise ValidationError("Tax percent does not match FDMS configuration")


def validate_hs_code_for_vat_taxpayer(receipt_line, tax_id, tax_percent, exempt_tax_ids):
    """
    VAT taxpayer HS code rule:
    - If Exempt or taxPercent == 0: receiptLineHSCode must be 8 digits.
    - If taxPercent > 0: 4 or 8 digits allowed.
    Raises ValidationError if invalid.
    """
    hs = receipt_line.get("receiptLineHSCode") or receipt_line.get("hs_code") or ""
    hs = str(hs).strip()
    if not hs:
        raise ValidationError("receiptLineHSCode is required")
    digits_only = "".join(c for c in hs if c.isdigit())
    length = len(digits_only)

    is_exempt_or_zero = int(tax_id) in exempt_tax_ids or (tax_percent is not None and float(tax_percent) == 0)
    if is_exempt_or_zero:
        if length != 8:
            raise ValidationError(
                f"Exempt/zero-rated line must have 8-digit HS code (got {length} digits: {hs})"
            )
    else:
        if length not in (4, 8):
            raise ValidationError(
                f"Taxable line must have 4 or 8-digit HS code (got {length} digits: {hs})"
            )
