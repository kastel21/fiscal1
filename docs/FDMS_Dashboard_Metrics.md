# FDMS Dashboard – Operational & Compliance Metrics (Cursor-Ready)

## Purpose
Introduce a **single dashboard** that gives instant visibility into:
- Fiscal compliance
- Operational health
- Accounting flow (QuickBooks)
- Risk & errors

This dashboard is **read-only**, safe for auditors, and useful for daily operations.

---

## Dashboard Audience
- Cashier (limited view)
- Accountant (financial + reconciliation)
- Admin (system + compliance)

---

## Core Principles

- No charts that hide detail
- Tables > graphs
- Clear status indicators
- Metrics must be explainable to an auditor

---

## Dashboard Layout (Top → Bottom)

### 1️⃣ System Status Strip (Always Visible)

Show as tiles:

- Fiscal Day Status: OPEN / CLOSED
- FDMS Connectivity: OK / ERROR
- Certificate Status: VALID / EXPIRING / EXPIRED
- Last GetStatus Sync Time

```json
{
  "fiscalDay": "OPEN",
  "fdms": "OK",
  "certificate": "EXPIRING (9 days)",
  "lastSync": "2026-02-06 14:32"
}
```

---

### 2️⃣ Today’s Fiscal Activity

Metrics:
- Invoices fiscalised today
- Credit notes issued today
- Total fiscal value (net)
- Total VAT declared today

Rules:
- Use FDMS-confirmed values only
- Credit notes subtract from totals

---

### 3️⃣ Receipt Pipeline Health

Metrics:
- Draft receipts
- Submitted (pending)
- Fiscalised
- Failed (retry required)

Display as:
- Numeric counts
- Clickable filters

---

### 4️⃣ QuickBooks Integration Status

Metrics:
- QB invoices received today
- QB invoices fiscalised
- QB invoices pending fiscalisation
- QB → FDMS failures

Show last webhook time.

---

### 5️⃣ Error & Risk Panel (Critical)

Metrics:
- Failed receipts (last 24h)
- CloseDay failures
- Certificate warnings
- Counter mismatches

Each row must link to:
- Error details
- operationID
- Retry action (role-based)

---

### 6️⃣ Compliance Snapshot

Show:
- Last successful OpenDay
- Last successful CloseDay
- Last receiptGlobalNo
- Any open fiscal risks

This section should be printable for audits.

---

## Role-Based Visibility

### Cashier
- Today’s invoices
- Pending receipts
- Cannot see certs or counters

### Accountant
- All financial metrics
- QB integration panel
- Credit notes

### Admin
- Everything
- Actions (retry, OpenDay, CloseDay)

---

## Backend API Endpoints

```http
GET /api/dashboard/summary
GET /api/dashboard/receipts
GET /api/dashboard/errors
GET /api/dashboard/quickbooks
```

All endpoints are read-only.

---

## Sample API Response

```json
{
  "today": {
    "invoices": 42,
    "creditNotes": 3,
    "netTotal": 12500.00,
    "vatTotal": 1875.00
  },
  "pipeline": {
    "draft": 2,
    "pending": 1,
    "failed": 0
  }
}
```

---

## React Implementation Notes

- Use cards for sections
- Use tables for lists
- No auto-refresh faster than 30s
- Highlight warnings only (no animations)

---

## Tests to Add

- Dashboard loads with no receipts
- Metrics match DB aggregates
- Role-based access enforced
- Failed receipts reflected correctly

---

## Action for Cursor

1. Create dashboard API endpoints
2. Aggregate FDMS-safe metrics
3. Build dashboard screen in React
4. Apply role-based visibility
5. Add tests for correctness

---

## One-Line Rule

> If the dashboard looks calm and boring, it’s doing its job.
