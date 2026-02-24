# FDMS Credit Note Implementation – Receipt Creation (Cursor-Ready)

## Purpose
Add **Credit Note support** to receipt creation by allowing users to choose between:
- Fiscal Invoice (Sale)
- Credit Note (Refund / Reversal)

This implementation is **FDMS-compliant**, user-friendly, and auditable.

---

## Business Rule (FDMS)

FDMS supports credit notes via:
- `receiptType = CreditNote`
- Negative receipt lines and totals
- Reference to the **original fiscal invoice**

A credit note is a **distinct fiscal document**, not a modified invoice.

---

## UI Changes – Receipt Creation Screen

### Receipt Type Selector

Add a radio button group:

```
Receipt Type:
(●) Fiscal Invoice
( ) Credit Note
```

Default:
- Fiscal Invoice

---

## Conditional UI Behavior

### Fiscal Invoice
- Standard behavior
- Positive quantities and amounts

### Credit Note
- Require original invoice reference
- UI shows positive values
- System converts values to negative internally

---

## Required Fields (Credit Note Only)

Displayed only when **Credit Note** is selected:

- Original Invoice Number (required)
- Original Receipt Global No (required)
- Original Receipt Date (optional)

---

## Backend Receipt Draft Model

```python
class ReceiptDraft(models.Model):
    receipt_type = models.CharField(
        max_length=20,
        choices=[
            ("FiscalInvoice", "Fiscal Invoice"),
            ("CreditNote", "Credit Note")
        ]
    )
    original_invoice_no = models.CharField(max_length=50, null=True, blank=True)
    original_receipt_global_no = models.CharField(max_length=20, null=True, blank=True)
```

---

## Receipt Build Logic (CRITICAL)

### Fiscal Invoice
- All amounts remain positive

### Credit Note (internal transform)

```python
for line in receipt_lines:
    line["receiptLineQuantity"] = -abs(line["receiptLineQuantity"])
    line["receiptLineTotal"] = -abs(line["receiptLineTotal"])

for tax in receipt_taxes:
    tax["taxAmount"] = -abs(tax["taxAmount"])
    tax["salesAmountWithTax"] = -abs(tax["salesAmountWithTax"])

receipt["receiptTotal"] = -abs(receipt["receiptTotal"])
```

---

## FDMS Payload Example (Credit Note)

```json
{
  "receiptType": "CreditNote",
  "invoiceNo": "CN-2026-001",
  "receiptLines": [
    {
      "receiptLineType": "Sale",
      "receiptLineName": "Returned bread",
      "receiptLineQuantity": -1.00,
      "receiptLineTotal": -44.00,
      "taxID": 1
    }
  ],
  "receiptTaxes": [
    {
      "taxID": 1,
      "taxAmount": -5.28,
      "salesAmountWithTax": -49.28
    }
  ],
  "receiptTotal": -49.28
}
```

---

## Validation Rules (HARD BLOCKS)

For Credit Notes:
- receiptType must be `CreditNote`
- Original invoice number required
- Original receiptGlobalNo required
- Original invoice must be fiscalized
- All totals must be negative
- Fiscal day must be OPEN

Failing any rule → **do not submit**

---

## SubmitReceipt Guard

```python
if receipt_type == "CreditNote":
    assert original_invoice_exists()
    assert original_invoice_fiscalized()
```

---

## Invoice Rendering

### Fiscal Invoice
- Title: **Fiscal Tax Invoice**

### Credit Note
- Title: **Fiscal Credit Note**
- Show:
  - Original invoice number
  - Original receiptGlobalNo

---

## QR Verification

- Credit Notes also receive:
  - receiptID
  - receiptQrData
- Generate QR exactly like invoices
- Verification page will show document type

---

## Health Panel Updates

Display:
- Count of Fiscal Invoices
- Count of Credit Notes
- Failed Credit Notes

---

## Action for Cursor

1. Add receipt type radio button
2. Add conditional credit note fields
3. Transform values internally
4. Add validation guards
5. Submit to FDMS using `receiptType=CreditNote`
6. Update invoice rendering
7. Add tests for invoice vs credit note

---

## One-Line Rule

> A credit note is a first-class fiscal document, not a modified invoice.
