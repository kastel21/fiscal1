# Excel Import UX – Credit Notes (FDMS-Safe, Cursor-Ready)

## Purpose
Define a **safe, compliant Excel import user experience for Credit Notes**, ensuring:
- No over-crediting
- Mandatory linkage to original fiscal invoice
- Full audit traceability
- Zero risk of illegal fiscal corrections

This UX sits on top of the reusable Excel Import Engine.

---

## Core Principle (Non‑Negotiable)

> A Credit Note MUST reference an existing fiscalised invoice and MUST NOT exceed its remaining balance.

If this cannot be satisfied, the import must be blocked.

---

## 1️⃣ Entry Point – Credit Note Import

### UI Action
Button visible to:
- Accountant
- Admin

```
[ Import Credit Note (Excel) ]
```

Cashiers must not see this action.

---

## 2️⃣ Step 1 – Select Original Fiscal Invoice

### Mandatory Selector
Before Excel upload, user must select:

- Original Invoice (searchable)
  - Invoice number
  - Receipt Global Number
  - Customer name
  - Original total
  - Remaining creditable balance

UI rule:
- Excel upload disabled until invoice is selected

---

## 3️⃣ Step 2 – Upload Excel File

### Allowed Content
- Credit note Excel
- Supplier-issued return / adjustment document

### Engine Behavior
- Use same header auto-detection logic as invoices
- Ignore non-line-item rows
- Treat all imported amounts as **credit values**

---

## 4️⃣ Step 3 – Credit Note Preview Screen

### Preview Table

| Qty | Description | Unit Price | Credit Amount |
|-----|------------|------------|---------------|

Rules:
- All totals displayed as positive numbers
- UI label clearly states **CREDIT**
- Rows derived from Excel highlighted (italic)

---

## 5️⃣ Step 4 – Mandatory Validation (Hard Blocks)

### Validation Rules

Block submission if:
- No original invoice selected
- Imported credit total > remaining invoice balance
- Credit lines do not match original invoice items (description similarity check)
- Any line total ≤ 0
- Tax not selected
- Currency mismatch with original invoice
- Fiscal day CLOSED
- Certificate expired

---

## 6️⃣ Step 5 – Credit Allocation Summary

Display a clear summary:

```
Original Invoice Total:      1,200.00
Already Credited:             200.00
This Credit Note:              300.00
Remaining After Credit:        700.00
```

User must confirm:
```
[ ] I confirm this credit note is correct and final
```

No checkbox → no submission.

---

## 7️⃣ Step 6 – Enrichment Panel

User must confirm:
- Tax treatment (must match original invoice)
- Payment reversal method (informational)
- Credit reason (free text, mandatory)

---

## 8️⃣ FDMS Mapping Rules (Authoritative)

- receiptType = CreditNote
- receiptLines:
  - Quantities positive
  - Line totals negative at FDMS layer
- receiptTotal negative
- Original receiptGlobalNo stored and linked

Never allow manual sign flipping.

---

## 9️⃣ Submission & Outcome

### On Success
- Credit note fiscalised
- Remaining balance updated
- Credit note PDF generated
- QR verification available

### On Failure
- No balance changes
- Retry allowed (admin only)
- Error logged with operationID

---

## 10️⃣ Audit & Persistence

Always store:
- Raw Excel file
- Parsed credit lines
- Original invoice snapshot
- Remaining balance calculation
- User confirmation & reason

These records are immutable.

---

## 11️⃣ UI Warnings (Always Visible)

Banner at top of preview:

```
⚠ Credit Note
This document reduces a previously fiscalised invoice.
Edits are not permitted after submission.
```

---

## 12️⃣ Tests to Add

### Backend
- Credit > remaining balance → blocked
- Currency mismatch → blocked
- Missing original invoice → blocked

### Frontend
- Upload disabled until invoice selected
- Confirmation checkbox enforced
- Balance summary accurate

---

## 13️⃣ Action for Cursor

1. Add Credit Note import entry point
2. Enforce original invoice selection
3. Reuse Excel parsing engine
4. Build credit preview + balance summary UI
5. Enforce all validation rules
6. Map correctly to FDMS Credit Note
7. Add audit persistence
8. Add tests

---

## One‑Line Rule

> A credit note may correct an invoice, but it must never rewrite fiscal history.
