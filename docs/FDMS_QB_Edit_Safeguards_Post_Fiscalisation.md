# Safeguards for QuickBooks Invoice Edits After Fiscalisation (Cursor-Ready)

## Core Rule

Once a QuickBooks invoice is fiscalised, **fiscal data must never change**.

---

## Blocked Changes

After fiscalisation:
- Line items
- Quantities
- Prices
- Taxes
- Currency
- Totals

Allowed:
- Payment status
- Notes
- Attachments

---

## Detection

On `Invoice.Update` webhook:

- Load fiscalised invoice
- Compare fiscal fields
- Detect differences

```python
if invoice.is_fiscalised and fiscal_fields_changed():
    block_or_flag()
```

---

## Enforcement Options

### Recommended: Hard Block
- Reject update
- Notify admin

Alternative: Soft Block
- Mark invoice as FISCAL MISMATCH
- Require credit note

---

## Correct Correction Flow

1. Create QuickBooks Credit Memo
2. Trigger FDMS Credit Note
3. (Optional) Create new invoice

---

## UI Warning

⚠ This invoice has been fiscalised.  
To correct it, issue a credit note.

---

## Audit Log

Log:
- Original snapshot
- Attempted change
- Actor
- Timestamp

---

## Action for Cursor

1. Add fiscalised flag
2. Add field-level diff
3. Enforce block rules
4. Add UI warnings
5. Log attempts

---

## One-Line Rule

> Fiscal records are immutable; corrections require credit notes.
