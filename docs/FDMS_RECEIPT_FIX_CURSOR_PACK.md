
# FDMS Receipt Fix – Cursor Implementation Pack

## Purpose
Fix SubmitReceipt validation errors:
- RCPT020 – Invoice signature not valid
- RCPT025 – Invalid tax is used
- RCPT026 – Incorrectly calculated tax amount
- RCPT027 – Incorrectly calculated total sales amount

---

## 1. Always Include previousReceiptHash

### Rule
- First receipt of fiscal day → DO NOT include previousReceiptHash
- All subsequent receipts → MUST include previousReceiptHash (base64 hash of previous receipt)

### Implementation
Store receiptDeviceSignature.hash after every successful submission.
Use it when building the next receipt canonical string.

---

## 2. Buyer Information Block (Recommended)

Include buyer when issuing tax invoice:

{
  "buyerData": {
    "buyerRegisterName": "Customer Name",
    "buyerTIN": "1234567890",
    "buyerVATNumber": "123456789",
    "buyerAddress": "Customer Address"
  }
}

Only include VAT number if buyer is VAT registered.

---

## 3. Correct Monetary Handling (CRITICAL)

Use Decimal + ROUND_HALF_UP everywhere.

Example:

from decimal import Decimal, ROUND_HALF_UP

def round2(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

Tax (exclusive mode):
tax_amount = round2(net_total * tax_percent / 100)

Tax (inclusive mode):
tax_amount = round2(gross_total - (gross_total / (1 + tax_percent/100)))

Never manually type taxAmount.
Always compute it.

---

## 4. Receipt Validation Guard (Before Submission)

Validate:

- line_total == quantity * unit_price
- taxAmount == calculated tax
- receiptTotal == sum(lineTotals + tax)
- paymentAmount == receiptTotal

Reject locally before calling FDMS if mismatch.

---

## 5. Canonical Signature Order

Concatenate EXACTLY in this order:

deviceID +
receiptType +
receiptCurrency +
receiptGlobalNo +
receiptDate +
receiptTotal (in cents) +
receiptTaxes block +
previousReceiptHash (if exists)

Hash = SHA256(concatenated_string)
Signature = Sign(concatenated_string)

---

## 6. Tax Rules

- Use numeric taxCode (e.g., "517")
- taxPercent must match taxID configuration
- salesAmountWithTax must equal receiptTotal (for single tax case)

---

## 7. Final Checklist

Before SubmitReceipt:

✔ previousReceiptHash included (if not first)
✔ VAT status verified
✔ TaxPercent matches taxID
✔ All amounts rounded to 2 decimals
✔ Canonical string matches spec order

---

END OF PACK
