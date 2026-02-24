# Invoice Number–Based Duplicate Prevention (FDMS-Safe) — Cursor-Ready MD

## Purpose
Enforce **invoice-number–based duplicate prevention** in a way that:
- Matches real accounting practice
- Is safe for FDMS fiscalisation
- Prevents double fiscalisation
- Supports Credit Notes correctly
- Works across Excel imports, manual entry, and QuickBooks

This MD formalises **invoice number as the primary uniqueness anchor**, with proper scope.

---

## Core Rule (Non-Negotiable)

> A fiscal invoice number may be used **only once per supplier** to generate a fiscal invoice.

Everything else must be blocked or explicitly linked as a credit note.

---

## 1️⃣ Canonical Uniqueness Constraint

### Database-Level Rule (Mandatory)

Create a unique constraint on:

```
(supplier_id, invoice_number, receipt_type)
```

Where:
- `receipt_type ∈ {FiscalInvoice, CreditNote}`

This allows:
- One fiscal invoice per invoice number
- Multiple credit notes with their own numbers

---

## 2️⃣ Invoice Number Extraction (Imports & UI)

### Sources
Invoice number may come from:
- Excel header / footer
- Manual entry form
- QuickBooks invoice number

Rules:
- Invoice number is **mandatory**
- Submission blocked if missing
- Whitespace trimmed
- Case-normalised

---

## 3️⃣ Duplicate Check — Excel Import (Early Block)

During Excel parsing:

```text
IF supplier + invoice_number + FiscalInvoice already exists
→ BLOCK import
```

UI message example:
> “Invoice INV-00123 has already been fiscalised on 2026-02-04 (Receipt #000000018).”

No override for cashiers.

---

## 4️⃣ Duplicate Check — Pre-FDMS Submission (Hard Block)

Before calling `SubmitReceipt`:

- Re-check uniqueness constraint
- Use database transaction / lock
- Abort submission if duplicate detected

This prevents:
- Race conditions
- Multi-user duplicates
- Retry-based duplicates

---

## 5️⃣ Credit Note Rules (Explicit & Separate)

Credit Notes MUST:
- Have their **own credit note number**
- Reference an existing fiscal invoice
- Never reuse the original invoice number as their own

Allowed:
```
Invoice:     INV-00123
Credit Note: CN-0045 → linked to INV-00123
```

Blocked:
```
Credit Note with invoice number = INV-00123
```

---

## 6️⃣ Additional Safety Layers (Recommended)

### Layer 2: File Hash (Excel)
- Hash raw Excel file
- Block re-upload of same file

### Layer 3: Business Fingerprint (Optional)
- Supplier
- Customer
- Date
- Normalised line items
- Grand total

Used as a warning layer, not primary enforcement.

---

## 7️⃣ What to Store (Audit Minimum)

For each fiscal document:
- supplier_id
- invoice_number
- receipt_type
- receiptGlobalNo
- fiscal_date
- source (Manual / Excel / QuickBooks)
- created_by
- created_at

These records are immutable.

---

## 8️⃣ UI Requirements

### Preview Screen
- Clearly show invoice number
- Warn if invoice number already exists
- Block submission if duplicate

### Error Messaging
Human-readable, example:
> “Invoice INV-00123 already exists and cannot be fiscalised again.”

No technical jargon.

---

## 9️⃣ Tests to Add

### Backend
- Duplicate invoice number → blocked
- Same invoice number, different supplier → allowed
- Credit note reusing invoice number → blocked

### Frontend
- Missing invoice number → submit disabled
- Duplicate detected → blocking banner

---

## 10️⃣ Action for Cursor

1. Add DB unique constraint
2. Enforce invoice number requirement everywhere
3. Implement early duplicate checks
4. Re-check before FDMS submission
5. Update import engines (Excel & QB)
6. Add automated tests

---

## One-Line Rule

> One invoice number, one fiscal invoice — everything else must be a credit note or be blocked.
