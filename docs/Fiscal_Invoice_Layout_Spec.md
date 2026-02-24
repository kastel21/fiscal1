# Fiscal Invoice Layout Specification (FDMS / ZIMRA)

## Scope
Defines the mandatory layout and content for a Fiscal Tax Invoice generated only after a successful SubmitReceipt (200 OK).

---
## Preconditions
- SubmitReceipt returned 200 OK
- receiptID is present
- receiptServerSignature is present

---
## Header (Required)
- Seller name, TIN, VAT
- Branch name & address
- Fiscal device serial & ID

---
## Invoice Identity
- Title: FISCAL TAX INVOICE
- receiptID
- receiptGlobalNo
- Internal invoice reference
- receiptDate
- Currency

---
## Line Items
Description, Qty, Unit Price, Net, Tax Rate, Tax Amount, Gross.

---
## Totals
Subtotal, Total Tax, Grand Total, Payment Method.

---
## Fiscal Validation
- FDMS receiptID
- FDMS server signature
- Verification QR

---
## Immutability
No edits after fiscalisation.

---
## Action for Cursor
Enforce layout, block download if fiscal data missing.
