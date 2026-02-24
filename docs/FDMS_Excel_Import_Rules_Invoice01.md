# Intelligent Excel Import – Invoice 01 (Laundry Bin / Flyquest) – Cursor-Ready MD

## Purpose
Define **exact import rules, UI behavior, auto-detection logic, and validation safeguards** for importing the provided Excel invoice:
`Quotation.. - Laundry Bin - Flyquest pty 2026.xlsx` → **Invoice 01** sheet.

This MD is tailored specifically to the structure and issues observed in that file, while remaining reusable for similar invoices.

---

## 1️⃣ Supported Sheets & Scope

### Allowed Sheets
- ✅ `Invoice 01` → importable
- ❌ `quote` → ignore (non-fiscal)
- ❌ `Delivery Note 1` → ignore (non-fiscal)

Hard rule:
> Only one invoice may be imported per operation.

---

## 2️⃣ Header Auto-Detection Logic (Messy Layout Safe)

This file does **not** have headers in row 1.

### Detection Algorithm
1. Scan first 30 rows
2. Identify row containing **at least 3 of the following keywords**:
   - qty
   - quantity
   - description
   - item
   - amount
   - total
   - uom

3. Treat this row as the header row
4. Data rows begin immediately after

```python
REQUIRED_HEADER_MATCHES = 3
```

---

## 3️⃣ Column Mapping Rules (Invoice 01)

| Excel Column (detected) | FDMS Field |
|------------------------|------------|
| Qty / Quantity | receiptLineQuantity |
| Description | receiptLineName |
| Amount Due / Unit Price | derived |
| Total | receiptLineTotal |
| UOM | ignored |
| Item No | optional (internal reference) |

Notes:
- Unit price may be derived as:  
  `line total ÷ quantity`
- Empty rows must be skipped automatically

---

## 4️⃣ Line Item Extraction Rules

A row is a **valid line item** if:
- Quantity > 0
- Line total > 0
- Description is not empty

Rows failing this → skipped with warning.

---

## 5️⃣ Import Preview Screen (UI Spec)

### Step 1: File Upload
- Show detected sheet: `Invoice 01`
- Show detected header row number
- Allow user to confirm

---

### Step 2: Preview Table (Mandatory)

Display a table:

| Qty | Description | Unit Price | Line Total |
|-----|------------|------------|------------|

Features:
- Highlight derived values (italic)
- Highlight mismatches in red
- No submission button yet

---

### Step 3: Enrichment Panel (Mandatory)

User must select / confirm:
- Receipt Type: Invoice / Credit Note
- Currency
- Tax Type (VAT / Zero-rated)
- Payment Method

These **cannot** be inferred from Excel.

---

## 6️⃣ Import Validation Rules (Hard Blocks)

### Block import if:
- qty × unit price ≠ line total (± rounding tolerance)
- Any line total ≤ 0
- No valid line items detected
- Tax not selected
- Currency not selected
- Fiscal day is CLOSED
- Certificate is expired

---

## 7️⃣ Totals Validation

Before enabling submission:
- Compute subtotal from imported lines
- Display computed totals
- User must explicitly confirm

No silent corrections allowed.

---

## 8️⃣ FDMS Preparation Rules

Before SubmitReceipt:
- Populate taxID from GetConfigs
- Populate receiptCurrency from UI
- Populate receiptLinesTaxInclusive = false (default)
- Do NOT generate receipt counters yet

Counters increment **only after FDMS success**.

---

## 9️⃣ Audit Safety Rules

- Store raw Excel file
- Store parsed line items snapshot
- Store user confirmations
- Never allow re-import of same file without warning

---

## 10️⃣ Error Messaging (Human-Friendly)

Example:
> “Row 12: Quantity × Unit Price does not equal Line Total. Please correct the Excel file or adjust values.”

No stack traces.

---

## 11️⃣ Tests to Add

- Header detection on Invoice 01
- Empty row skipping
- Unit price derivation
- Validation failure on missing tax
- Successful import → preview → submit

---

## 12️⃣ Action for Cursor

1. Implement header auto-detection
2. Implement column mapping logic above
3. Build preview + enrichment UI
4. Enforce validation rules
5. Block submission until all checks pass
6. Log and persist import artifacts

---

## One-Line Rule

> Excel files are suggestions; fiscal invoices require explicit validation and confirmation.
