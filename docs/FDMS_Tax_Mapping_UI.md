# FDMS Tax Mapping UI (Cursor-Ready)

## Purpose
Provide a UI to map **internal / QuickBooks tax codes** to **FDMS taxIDs**
returned by `GetConfigs`.

This prevents invalid tax usage and submission failures.

---

## Data Model

### FDMS Tax Mapping
```python
class FDMSTaxMapping(models.Model):
    device_id = models.CharField(max_length=50)
    source_system = models.CharField(max_length=50)  # e.g. QuickBooks
    source_tax_code = models.CharField(max_length=50)
    fdms_tax_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## UI Layout

### Tax Mapping Screen

```
--------------------------------------------------
Source System: [ QuickBooks ▼ ]
--------------------------------------------------
QuickBooks Tax Code | FDMS Tax ID | FDMS Rate
--------------------------------------------------
VAT 15%            | 1           | 15%
Zero Rated         | 2           | 0%
Exempt             | 3           | 0%
--------------------------------------------------
[ Save Mappings ]
```

---

## UI Rules

- FDMS taxID dropdown populated ONLY from GetConfigs
- Show FDMS tax rate next to taxID
- Prevent saving invalid mappings
- Highlight unmapped taxes

---

## Backend API

### GET /api/fdms/tax-configs
Returns FDMS tax table from latest GetConfigs.

### GET /api/fdms/tax-mappings
Returns saved mappings.

### POST /api/fdms/tax-mappings
Saves mappings with validation.

---

## Receipt Build Integration

```python
def map_tax(source_tax_code):
    mapping = get_mapping(source_tax_code)
    if not mapping:
        raise ValidationError("Tax not mapped to FDMS taxID")
    return mapping.fdms_tax_id
```

Receipts must:
- Use mapped FDMS taxID
- Never accept free-text tax IDs

---

## Health Panel Integration

Show:
- Number of unmapped taxes
- Last mapping update time
- Warning if mappings incomplete

---

## Action for Cursor

1. Build tax mapping UI
2. Populate FDMS tax IDs from GetConfigs
3. Enforce mapping during receipt creation
4. Block SubmitReceipt if tax unmapped
5. Add tests for mapping enforcement

---

## Result

- Tax compliance guaranteed
- No FDMS tax-related rejections
- Clear operator control
- Production-safe integration

