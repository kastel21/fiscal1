# Invoice Preview – Synced from QuickBooks (Cursor-Ready)

## Purpose
Clearly indicate that a fiscal invoice was **originated from QuickBooks**, while preserving FDMS as the fiscal authority.

---

## Mandatory Source Banner

Display at the top of the Invoice Preview:

🟦 **Synced from QuickBooks**  
This invoice was generated in QuickBooks and fiscalised via ZIMRA FDMS.

Must appear in:
- Web preview
- PDF
- Printed invoice

---

## Header Fields

Show:
- Fiscal Document Type
- FDMS Receipt Global Number
- Fiscalisation Date
- Source System: QuickBooks
- QuickBooks Invoice ID

---

## Line Items

- Read-only
- Exactly as received from QuickBooks
- No recalculation

---

## QR & Verification

- Display FDMS QR code
- Show verification URL text

---

## UI Rules

- No edit actions
- Re-download and re-print allowed

---

## Action for Cursor

1. Add QuickBooks source banner
2. Include QB invoice reference
3. Render banner in PDF template
4. Lock invoice view

---

## One-Line Rule

> If it came from QuickBooks, the invoice must say so forever.
