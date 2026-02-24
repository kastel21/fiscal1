
# FDMS SUBMITRECEIPT DUAL-MODE FIX PACK
## Exact Implementation Instructions (Retail + Tax Invoice)

---

# 🎯 PROBLEM THIS FIX SOLVES

You are experiencing:

- Mandatory buyer data fields are not provided
- Wrong receiptType usage
- VAT mismatch issues
- Signature validation failures after adding buyer data

This document gives exact implementation steps to fix it properly.

---

# ✅ STEP 1 — NEVER LET FRONTEND SEND receiptType

Frontend must send:

issueTaxInvoice: boolean

DO NOT accept receiptType directly from UI.

---

# ✅ STEP 2 — BACKEND MUST CONTROL receiptType

Implement:

```python
def resolve_receipt_type(issue_tax_invoice: bool) -> str:
    return "FISCALINVOICE" if issue_tax_invoice else "FISCALRECEIPT"
```

Use this inside your receipt builder.

---

# ✅ STEP 3 — BUYER DATA RULES (CRITICAL)

## If receiptType = FISCALRECEIPT

DO NOT include buyerData block at all.

Remove it completely.

---

## If receiptType = FISCALINVOICE

buyerData block is mandatory.

Include EXACT structure:

```json
"buyerData": {
  "buyerRegisterName": "Customer Name",
  "buyerTIN": "1234567890",
  "buyerVATNumber": "",
  "buyerAddress": "Harare, Zimbabwe"
}
```

Rules:
- Do NOT omit fields
- Do NOT send null
- If buyer not VAT registered → send empty string for VAT number
- All fields must be non-null strings

---

# ✅ STEP 4 — STORE VAT STATUS DURING DEVICE REGISTRATION

When calling verifyTaxpayerInformation:

```python
device.is_vat_registered = bool(response.get("vatNumber"))
```

Persist this in database.

---

# ✅ STEP 5 — BLOCK VAT IF TAXPAYER NOT VAT REGISTERED

Before SubmitReceipt:

```python
if not device.is_vat_registered and receipt_contains_vat():
    raise ValidationError("VAT not allowed for non-VAT taxpayer")
```

Also disable VAT selection in UI.

---

# ✅ STEP 6 — SIGNATURE SAFETY

Canonical order (Section 13.2.1):

deviceID +
receiptType +
receiptCurrency +
receiptGlobalNo +
receiptDate +
receiptTotal (in cents) +
receiptTaxes +
previousReceiptHash (if exists)

Buyer fields are NOT part of canonical string.

⚠ After adding or removing buyerData:
You MUST regenerate:
- canonical string
- SHA256 hash
- signature

---

# ✅ STEP 7 — SAFE RECEIPT BUILDER TEMPLATE

```python
def build_receipt(issue_tax_invoice, buyer_data=None):
    receipt_type = resolve_receipt_type(issue_tax_invoice)

    receipt = {
        "deviceID": device.id,
        "receiptType": receipt_type,
        "receiptCurrency": "USD",
        # other required fields
    }

    if receipt_type == "FISCALINVOICE":
        if not buyer_data:
            raise ValueError("Buyer data required for tax invoice")
        receipt["buyerData"] = buyer_data

    return receipt
```

---

# ✅ STEP 8 — PRE-SUBMIT VALIDATION CHECKLIST

Before calling FDMS:

✔ receiptType resolved internally
✔ buyerData present ONLY for FISCALINVOICE
✔ VAT usage matches taxpayer VAT status
✔ receiptTotal equals sum(lines + tax)
✔ previousReceiptHash chained correctly
✔ Signature regenerated AFTER final payload build

---

# ✅ FINAL EXPECTED BEHAVIOR

Retail sale:
- receiptType = FISCALRECEIPT
- No buyerData
- VAT allowed only if taxpayer VAT registered

Tax invoice:
- receiptType = FISCALINVOICE
- buyerData mandatory
- Signature regenerated

---

END OF FIX PACK
