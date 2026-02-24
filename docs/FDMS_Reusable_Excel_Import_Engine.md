# Reusable Excel Import Engine (Multi‑Supplier, FDMS‑Safe) — Cursor‑Ready

## Purpose
Provide a **single, reusable Excel import engine** that supports:
- Multiple suppliers
- Messy Excel layouts
- Invoice and Credit Note imports
- Strict FDMS compliance
- Audit safety

This spec applies to **any commercial Excel invoice**, not just Flyquest.

---

## 1️⃣ Supported Import Types

- Fiscal Invoice
- Credit Note (linked to original invoice)

Import type is **explicitly selected by the user** — never inferred.

---

## 2️⃣ Sheet Selection Rules

- Scan all sheets
- Rank sheets by likelihood of being an invoice:
  - Contains headers like: invoice, qty, description, total
- Present ranked list to user
- User must confirm selected sheet

Never auto‑submit.

---

## 3️⃣ Header & Column Auto‑Detection (Core Engine)

### Header Row Detection
1. Scan first 50 rows
2. Score rows based on keyword matches:
   - qty / quantity
   - description / item
   - amount / total / price
3. First row with ≥3 matches = header row

### Column Mapping Heuristics
| Detected Column | Canonical Field |
|----------------|-----------------|
| qty / quantity | quantity |
| description | description |
| amount / unit price | unit_price |
| total | line_total |
| tax | optional |
| uom | ignored |

Mappings are shown to user for confirmation.

---

## 4️⃣ Line Item Extraction Rules

A row is valid if:
- quantity > 0
- description present
- line_total > 0

Skip:
- Empty rows
- Notes
- Totals rows

Derive unit price if missing:
```
unit_price = line_total / quantity
```

---

## 5️⃣ React Import Preview Screen (Component Spec)

### Component: `ExcelImportPreview.tsx`

```tsx
export function ExcelImportPreview({ lines, onConfirm }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Import Preview</h2>

      <table className="w-full border">
        <thead>
          <tr>
            <th>Qty</th>
            <th>Description</th>
            <th>Unit Price</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} className={l.invalid ? "bg-red-50" : ""}>
              <td>{l.qty}</td>
              <td>{l.description}</td>
              <td>{l.unitPrice}</td>
              <td>{l.total}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <button onClick={onConfirm} className="btn-primary">
        Continue to Fiscalisation
      </button>
    </div>
  )
}
```

Preview is **read‑only**.

---

## 6️⃣ Mandatory Enrichment Panel

User must select:
- Receipt Type (Invoice / Credit Note)
- Currency
- Tax Type (VAT / Zero)
- Payment Method

Submission disabled until complete.

---

## 7️⃣ Import Validation Rules (Hard Blocks)

Block import if:
- qty × unit_price ≠ line_total (± tolerance)
- No valid line items
- Missing tax selection
- Missing currency
- Fiscal day CLOSED
- Certificate expired

---

## 8️⃣ Credit Note Import Variant

### Additional Requirements
- User must select original fiscal invoice
- Imported credit total ≤ remaining invoice balance
- Lines must reference original invoice items

### Mapping
- receiptType = CreditNote
- Negative totals enforced
- Original receiptGlobalNo stored

---

## 9️⃣ Audit & Persistence Rules

Always store:
- Raw Excel file
- Parsed snapshot
- User mappings
- User confirmations

Prevent duplicate imports:
- Hash file contents
- Warn on re‑import

---

## 🔁 Automated Import Validation Tests

### Backend (Django)

```python
def test_excel_import_validation():
    lines = parse_excel("sample.xlsx")
    assert all(l.total > 0 for l in lines)

def test_credit_note_over_limit_blocked():
    assert raises(ValidationError)
```

### Frontend
- Preview renders
- Invalid rows highlighted
- Submit blocked until valid

---

## 10️⃣ Action for Cursor

1. Implement reusable parser
2. Implement header auto‑detection
3. Build preview UI
4. Enforce enrichment & validation
5. Support invoice + credit note flows
6. Add automated tests

---

## One‑Line Rule

> Excel is a suggestion; fiscalisation requires validation, enrichment, and human confirmation.
