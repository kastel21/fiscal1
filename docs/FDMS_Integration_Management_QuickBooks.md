# Integration Management Page – Accounting Software (QuickBooks First)

## Purpose
Provide a **central Integration Management page** that allows administrators to:
- Connect accounting software (starting with QuickBooks)
- Monitor sync health
- Control fiscalisation behavior
- Safely expand to other accounting systems in the future

This page is **configuration + monitoring only** — no fiscal actions occur here.

---

## 1️⃣ Access & Roles

### Who Can Access
- ✅ Admin
- ✅ Accountant
- ❌ Cashier

---

## 2️⃣ Page Location

```
Settings → Integrations → Accounting Software
```

---

## 3️⃣ Integration Overview Panel

### Card: QuickBooks

Display a status card with:

- Integration Name: **QuickBooks Online**
- Connection Status:
  - Connected / Disconnected / Error
- Company Name (from QB)
- Company ID
- Environment: Sandbox / Production
- Last Sync Timestamp

### Actions
- [ Connect ]
- [ Reconnect ]
- [ Disconnect ] (Admin only)

---

## 4️⃣ Connection Configuration (QuickBooks)

### Required Fields
- Client ID
- Client Secret
- Redirect URI (read-only)
- Environment selector (Sandbox / Production)

OAuth flow only — no manual token entry.

---

## 5️⃣ Sync Behavior Configuration

### Invoice Sync Rules
Admin-configurable toggles:

- ✅ Auto-fiscalise when QB invoice is created
- ⛔ Do NOT fiscalise drafts
- ⛔ Do NOT fiscalise estimates
- ✅ Fiscalise only when status = Approved

---

### Invoice Number Mapping (Critical)

Display mapping clearly:

```
QuickBooks Invoice Number → FDMS Invoice Number
```

Rules:
- Mapping is mandatory
- Invoice number uniqueness enforced
- No manual override allowed

---

## 6️⃣ Tax Mapping Panel

### UI
Table mapping:

| QuickBooks Tax Code | FDMS Tax ID | Status |
|--------------------|------------|--------|
| VAT 15%            | 1          | OK     |
| Zero Rated         | 2          | OK     |
| Unmapped           | —          | ERROR  |

Rules:
- All QB tax codes must be mapped
- Unmapped codes block fiscalisation

---

## 7️⃣ Webhook Management Panel

### Show:
- Webhook subscription status
- Last webhook received
- Webhook event types:
  - Invoice Created
  - Invoice Updated
  - Invoice Deleted

### Controls
- [ Test Webhook ]
- [ Replay Last Event ]
- [ View Payload ]

---

## 8️⃣ Sync Health & Error Monitoring

### Metrics
- Invoices received today
- Successfully fiscalised
- Pending
- Failed

### Error Table
Columns:
- Timestamp
- QB Invoice #
- Error Type
- Action Required

Errors must link to retry / resolution screen.

---

## 9️⃣ Safeguards (Mandatory)

### After Fiscalisation
- QB invoice edits are blocked OR warned
- UI shows:
  > “This invoice has been fiscalised. Changes require a credit note.”

### Duplicate Protection
- Invoice number uniqueness enforced
- Re-sync does not create duplicates

---

## 🔮 10️⃣ Future-Proofing (Other Accounting Systems)

Architecture rules:
- One integration = one adapter
- Common interface:
  - fetch_invoices()
  - fetch_taxes()
  - verify_invoice_state()

UI:
- Same page
- Same layout
- Multiple cards (QuickBooks, Xero, Sage, etc.)

QuickBooks remains reference implementation.

---

## 11️⃣ Tests to Add

- OAuth connect / disconnect
- Webhook receipt
- Tax mapping validation
- Duplicate invoice prevention
- Auto-fiscalisation toggle behavior

---

## 12️⃣ Action for Cursor

1. Create Integration Management page
2. Implement QuickBooks card
3. Add OAuth flow
4. Add tax mapping UI
5. Add webhook monitor
6. Add sync health metrics
7. Enforce safeguards

---

## One-Line Rule

> Accounting integrations may feed invoices, but only FDMS decides what becomes fiscal.
