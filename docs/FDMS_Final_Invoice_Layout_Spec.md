# Fiscalised Invoice Layout Specification (Final, Clean)

## Purpose
Define the minimal, compliant, audit-safe layout for a ZIMRA FDMS fiscalised invoice.
Anything not listed here must not appear on the invoice.

---

## Mandatory Sections (Render in This Order)

### Supplier / Device Identity
- Registered Business Name
- Business Address
- VAT / Taxpayer Number
- FDMS Device ID

### Fiscal Header
- Document Type (Fiscal Tax Invoice / Credit Note)
- Receipt Global Number
- Fiscalisation Date & Time (FDMS)
- Receipt Currency

### Customer Information (Optional)
- Customer Name
- Customer Address

### Line Items
- Description
- Quantity
- Unit Price
- Line Total
- Tax Rate / Tax Code

### Tax Summary
- Tax Rate
- Taxable Amount
- Tax Amount
- Total Tax

### Totals
- Subtotal
- Total Tax
- Grand Total

### Payment Summary
- Payment Method
- Amount Paid

### QR Verification
- FDMS QR Code
- Verification text

### Source Metadata (Optional)
- Synced from QuickBooks
- QuickBooks Invoice Number

---

## Forbidden Content (Never Render)

- operationID
- receiptID
- receiptServerSignature
- receiptDeviceSignature
- hashes
- internal UUIDs
- debug or API status text

---

## Immutability Rules

- Fiscalised invoices are read-only
- Preview must exactly match PDF

---

## One-Line Rule

If it does not help a tax officer verify the invoice, it does not belong on the invoice.
