# FDMS – Enforce GetConfigs as Source of Truth (Cursor-Ready)

## Purpose
Make FDMS `GetConfigs` the **authoritative source of truth** for:
- Allowed tax IDs
- Tax rates
- Currency
- Receipt constraints

After this is implemented, **no receipt can be signed or submitted** unless it fully complies with the latest configs.

---

## System Rule (NON-NEGOTIABLE)

> If `GetConfigs` data is missing, stale, or violated, **SubmitReceipt must be blocked by your system**.

FDMS should never be the first place errors are detected.

---

## Required Data Model

### FDMSConfigs
```python
class FDMSConfigs(models.Model):
    device_id = models.CharField(max_length=50)
    raw_response = models.JSONField()
    tax_table = models.JSONField()
    allowed_currencies = models.JSONField()
    fetched_at = models.DateTimeField()
```
---

## Config Freshness Rule

Configs are considered **stale** if:
- Older than 24 hours
- OR device was restarted
- OR FDMS returns config version mismatch

```python
def configs_are_fresh(configs):
    return timezone.now() - configs.fetched_at < timedelta(hours=24)
```

---

## Backend Enforcement (CRITICAL)

### Before building or signing a receipt

```python
def validate_against_configs(receipt, configs):
    # currency
    if receipt["receiptCurrency"] not in configs.allowed_currencies:
        raise ValidationError("Currency not allowed by FDMS configs")

    # tax IDs
    valid_tax_ids = {t["taxID"] for t in configs.tax_table}
    for line in receipt["receiptLines"]:
        if line["taxID"] not in valid_tax_ids:
            raise ValidationError("Invalid taxID per FDMS configs")

    # tax math
    for tax in receipt["receiptTaxes"]:
        cfg = find_tax_config(tax["taxID"])
        assert math_matches(cfg, tax)
```

If validation fails:
- Do NOT sign
- Do NOT submit
- Return a clear error to UI

---

## SubmitReceipt Guard

```python
def submit_receipt(request):
    configs = get_latest_configs()
    if not configs or not configs_are_fresh(configs):
        return error("FDMS configs missing or stale")

    validate_against_configs(receipt, configs)
    return fdms_client.submit_receipt(...)
```

---

## UI Rules

- SubmitReceipt button disabled if configs missing/stale
- Health panel must show:
  - Config status: OK / STALE / MISSING
  - Last config sync time

---

## Action for Cursor

1. Persist GetConfigs responses
2. Parse and store tax table
3. Enforce validation before signing
4. Block SubmitReceipt on config violation
5. Add automated tests for enforcement

---

## Result

- No more blind submissions
- Fewer 422/500 errors
- Predictable FDMS behavior
- Audit-ready compliance

