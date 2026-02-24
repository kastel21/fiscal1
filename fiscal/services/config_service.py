"""
FDMS GetConfigs as source of truth. Persist, validate, enforce.
If configs are missing or stale, SubmitReceipt must be blocked.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from fiscal.models import FDMSConfigs, TaxMapping


def configs_are_fresh(configs: FDMSConfigs | None) -> bool:
    """Configs are stale if older than 24 hours."""
    if not configs:
        return False
    return timezone.now() - configs.fetched_at < timedelta(hours=24)


def persist_configs(device_id: int, raw_response: dict) -> FDMSConfigs:
    """
    Store latest GetConfig response whenever GetConfig is called.
    Extracts applicableTaxes to tax_table for the tax dropdown on invoice creation.
    Updates existing config for device or creates new (one latest per device).
    """
    tax_table = raw_response.get("applicableTaxes") or raw_response.get("taxTable") or []
    allowed = raw_response.get("allowedCurrencies")
    if allowed is None:
        allowed = ["USD", "ZWG"]
    allowed = allowed if isinstance(allowed, list) else list(allowed)
    now = timezone.now()

    existing = FDMSConfigs.objects.filter(device_id=device_id).order_by("-fetched_at").first()
    if existing:
        existing.raw_response = raw_response
        existing.tax_table = tax_table
        existing.allowed_currencies = allowed
        existing.fetched_at = now
        existing.save()
        return existing
    return FDMSConfigs.objects.create(
        device_id=device_id,
        raw_response=raw_response,
        tax_table=tax_table,
        allowed_currencies=allowed,
        fetched_at=now,
    )


def get_latest_configs(device_id: int | None = None) -> FDMSConfigs | None:
    """Return most recent configs for device. If device_id is None, use first registered device."""
    if device_id is not None:
        return FDMSConfigs.objects.filter(device_id=device_id).order_by("-fetched_at").first()
    return FDMSConfigs.objects.order_by("-fetched_at").first()


def get_tax_table_from_configs(configs: FDMSConfigs | None) -> list:
    """
    Extract tax options (applicableTaxes) from stored GetConfig for the tax dropdown.
    Uses tax_table if populated, else falls back to raw_response.applicableTaxes.
    """
    if not configs:
        return []
    tax_table = configs.tax_table or []
    if not tax_table and configs.raw_response:
        tax_table = configs.raw_response.get("applicableTaxes") or configs.raw_response.get("taxTable") or []
    return tax_table if isinstance(tax_table, list) else []


def validate_against_configs(
    receipt_currency: str,
    receipt_taxes: list[dict],
    receipt_lines: list[dict],
    configs: FDMSConfigs,
) -> None:
    """
    Validate receipt against FDMS configs. Raises ValidationError on violation.
    Do NOT sign or submit if this raises.
    """
    if not configs:
        raise ValidationError("FDMS configs missing")

    valid_tax_ids = {t.get("taxID") for t in (configs.tax_table or []) if t.get("taxID") is not None}
    if not valid_tax_ids:
        valid_tax_ids = {1}  # fallback if config has no taxID (e.g. old format)

    if configs.allowed_currencies and receipt_currency not in list(configs.allowed_currencies):
        raise ValidationError(
            f"Currency '{receipt_currency}' not allowed by FDMS configs. Allowed: {configs.allowed_currencies}"
        )

    valid_tax_codes = {str(t.get("taxCode", "") or "").strip().upper() for t in (configs.tax_table or []) if t.get("taxCode")}
    for tax in receipt_taxes or []:
        tid = tax.get("taxID")
        if tid is not None and tid not in valid_tax_ids:
            raise ValidationError(f"Invalid taxID {tid} per FDMS configs. Valid: {valid_tax_ids}")
        tax_code = tax.get("taxCode")
        if tax_code and valid_tax_codes and tid is None:
            if str(tax_code).strip().upper() not in valid_tax_codes:
                raise ValidationError(f"Invalid taxCode '{tax_code}' per FDMS configs. Valid: {valid_tax_codes}")

    for line in receipt_lines or []:
        tid = line.get("taxID")
        if tid is not None and tid not in valid_tax_ids:
            raise ValidationError(f"Invalid taxID {tid} in receipt line per FDMS configs")
        tax_code = line.get("taxCode") or line.get("receiptLineTaxCode")
        if tax_code and valid_tax_codes and str(tax_code).strip().upper() not in valid_tax_codes:
            raise ValidationError(
                f"Invalid taxCode '{tax_code}' per FDMS configs. Valid: {valid_tax_codes}"
            )


TAX_CODE_MAX_LENGTH = 3  # FDMS ReceiptLineDto/ReceiptTaxDto taxCode maxLength


def get_local_code_to_fdms_tax(configs: FDMSConfigs | None) -> dict[str, tuple[int, str | None]]:
    """
    From TaxMapping: local_code_upper -> (fdms_tax_id, fdms_tax_code_override or None).
    Used to resolve product tax_code to FDMS taxID. Override used when TaxMapping has fdms_tax_code.
    """
    mappings = TaxMapping.objects.filter(is_active=True)
    result = {}
    for m in mappings:
        key = str(m.local_code or "").strip().upper()
        if not key:
            continue
        override = (str(m.fdms_tax_code or "").strip()[:TAX_CODE_MAX_LENGTH]) or None
        result[key] = (m.fdms_tax_id, override)
    return result


def get_tax_id_to_code(configs: FDMSConfigs | None) -> dict[int, str]:
    """Map taxID -> taxCode from GetConfig tax_table. taxCode is max 3 chars.
    Uses taxName as fallback when taxCode missing (e.g. 0% EXEMPT)."""
    if not configs or not configs.tax_table:
        return {}
    result = {}
    for t in configs.tax_table:
        tid = t.get("taxID")
        if tid is None:
            continue
        raw = t.get("taxCode") or t.get("taxName")
        if not raw:
            continue
        code = str(raw).strip()[:TAX_CODE_MAX_LENGTH]
        if code:
            result[int(tid)] = code
    return result


def get_tax_id_to_percent(configs: FDMSConfigs | None) -> dict[int, float]:
    """Map taxID -> taxPercent from GetConfig tax_table. Exempt (taxName or no percent) maps to 0.0."""
    if not configs or not configs.tax_table:
        return {1: 15.0}
    result = {}
    for t in configs.tax_table:
        tid = t.get("taxID")
        if tid is None:
            continue
        name = (t.get("taxName") or "").strip().lower()
        pct = t.get("taxPercent") or t.get("fiscalCounterTaxPercent")
        if name == "exempt" or pct is None:
            val = 0.0
        else:
            val = float(pct)
        result[int(tid)] = round(val, 2)
    return result if result else {1: 15.0}


def get_tax_code_and_percent_for_id(device_id: int | None, tax_id: int) -> tuple[str, float]:
    """Get tax_code and tax_percent for tax_id. Prefers TaxMapping, else GetConfig."""
    configs = get_latest_configs(device_id)
    for m in TaxMapping.objects.filter(fdms_tax_id=tax_id, is_active=True):
        code = (str(m.fdms_tax_code or m.local_code or "").strip()[:TAX_CODE_MAX_LENGTH]) or "VAT"
        pct = float(m.tax_percent) if m.tax_percent is not None else 15.0
        return code, round(pct, 2)
    id_to_code = get_tax_id_to_code(configs)
    id_to_pct = get_tax_id_to_percent(configs)
    return (
        id_to_code.get(tax_id) or ("EXM" if id_to_pct.get(tax_id, 15) == 0 else "VAT"),
        id_to_pct.get(tax_id, 15.0),
    )


def enrich_receipt_taxes_with_tax_id(configs: FDMSConfigs | None, receipt_taxes: list[dict]) -> list[dict]:
    """
    Add taxID to receipt_taxes that have taxCode but not taxID.
    Prefers TaxMapping (Settings → Tax Mapping) when local code matches.
    Overwrites taxCode with GetConfig or TaxMapping override (FDMS source of truth).
    """
    if not receipt_taxes:
        return list(receipt_taxes)
    tax_table = (configs.tax_table or []) if configs else []
    local_to_fdms = get_local_code_to_fdms_tax(configs)
    code_to_id = {}
    pct_to_id = {}
    tax_id_to_code = get_tax_id_to_code(configs) if configs else {}
    for t in tax_table:
        tid = t.get("taxID")
        if tid is None:
            continue
        raw = t.get("taxCode")
        if raw is not None:
            code = str(raw).strip()[:TAX_CODE_MAX_LENGTH].upper()
            if code and code not in code_to_id:
                code_to_id[code] = int(tid)
        pct = t.get("taxPercent") or t.get("fiscalCounterTaxPercent")
        if pct is not None:
            pct_to_id[float(pct)] = int(tid)
    default_tid = next((t.get("taxID") for t in tax_table if t.get("taxID") is not None), 1) if tax_table else 1
    result = []
    for tax in receipt_taxes:
        out = dict(tax)
        if out.get("taxID") is None:
            code = str(out.get("taxCode", "") or "").strip().upper()[:TAX_CODE_MAX_LENGTH]
            pct = out.get("taxPercent")
            if code in local_to_fdms:
                out["taxID"] = local_to_fdms[code][0]
            else:
                out["taxID"] = (
                    code_to_id.get(code)
                    or (pct_to_id.get(float(pct)) if pct is not None else None)
                    or default_tid
                )
        tid = out.get("taxID")
        if tid is not None:
            local_code = str(out.get("taxCode", "") or "").strip().upper()[:TAX_CODE_MAX_LENGTH]
            override = local_to_fdms.get(local_code, (None, None))[1] if local_code else None
            out["taxCode"] = override or tax_id_to_code.get(tid) or str(tid)
        result.append(out)
    return result


def get_config_status(device_id: int | None = None) -> dict:
    """Return config status for UI: status (OK|STALE|MISSING), lastSync, configs."""
    configs = get_latest_configs(device_id)
    if not configs:
        return {"status": "MISSING", "lastSync": None, "configs": None}
    status = "OK" if configs_are_fresh(configs) else "STALE"
    return {
        "status": status,
        "lastSync": configs.fetched_at.isoformat(),
        "configs": configs,
    }
