# FDMS Dashboard – Full Implementation (Cursor-Ready)

## Purpose
Implement a **production-grade FDMS Dashboard** that provides:
- Operational visibility
- Fiscal compliance confidence
- QuickBooks integration insight
- Audit-ready exports
- Proactive alerts

This dashboard is **read-only**, accurate, and safe for auditors.

---

## Scope (What This MD Covers)

✔ React dashboard UI (Tailwind + cards)  
✔ Time-range filters (Today / Week / Month)  
✔ Accuracy & regression tests  
✔ Export to PDF / Excel  
✔ In-app + email alerts for critical states  

---

# 1️⃣ Dashboard Layout (React + Tailwind)

## Page Structure

```
Dashboard
 ├─ Status Strip
 ├─ Key Metrics
 ├─ Receipt Pipeline
 ├─ QuickBooks Integration
 ├─ Errors & Risks
 └─ Compliance Snapshot
```

---

## React Page Component

```tsx
export default function DashboardPage() {
  const [range, setRange] = useState("today")
  const { data } = useDashboard(range)

  return (
    <div className="space-y-6">
      <Header title="System Dashboard">
        <TimeRangeFilter value={range} onChange={setRange} />
      </Header>

      <StatusStrip data={data.status} />
      <MetricsGrid data={data.metrics} />
      <PipelineTable data={data.pipeline} />
      <ErrorTable errors={data.errors} />
      <ComplianceSnapshot data={data.compliance} />
    </div>
  )
}
```

---

# 2️⃣ Time-Range Filters

## UI

- Today
- This Week
- This Month

```tsx
<TimeRangeFilter value={range} onChange={setRange} />
```

## Backend

```http
GET /api/dashboard/summary?range=today|week|month
```

All aggregates must use **FDMS-confirmed data only**.

---

# 3️⃣ Metrics Definition (Authoritative)

### Status Strip
- Fiscal Day: OPEN / CLOSED
- FDMS Connectivity: OK / ERROR
- Certificate: VALID / EXPIRING / EXPIRED
- Last Sync Time

### Key Metrics
- Invoices fiscalised
- Credit notes issued
- Net fiscal total
- VAT declared

### Pipeline
- Draft
- Pending
- Fiscalised
- Failed

### QuickBooks
- Invoices received
- Fiscalised
- Pending
- Failed

### Compliance Snapshot
- Last OpenDay
- Last CloseDay
- Last receiptGlobalNo
- Outstanding risks

---

# 4️⃣ Accuracy & Regression Tests

## Backend (Django)

```python
def test_dashboard_totals():
    create_invoice(total=100, vat=15)
    create_credit_note(total=-20, vat=-3)

    res = client.get("/api/dashboard/summary?range=today").json()
    assert res["metrics"]["netTotal"] == 80
    assert res["metrics"]["vatTotal"] == 12
```

## Rules
- Dashboard values MUST match persisted FDMS data
- Draft receipts MUST NOT affect totals

---

# 5️⃣ Export to PDF / Excel (Audit-Ready)

## Endpoints

```http
GET /api/dashboard/export/pdf?range=month
GET /api/dashboard/export/excel?range=month
```

## PDF Must Include
- Period covered
- Fiscal day state
- Totals
- Last receiptGlobalNo
- Certificate status
- Generated timestamp

## Excel Sheets
1. Summary
2. Invoices
3. Credit Notes
4. Errors

Exports are **read-only and immutable**.

---

# 6️⃣ Alerts (In-App + Email)

## Alert Triggers

| Condition | Severity |
|--------|----------|
| Cert expires <14 days | WARNING |
| Cert expired | CRITICAL |
| CloseDay failure | CRITICAL |
| Failed receipts > 0 | WARNING |
| Counter mismatch | CRITICAL |

---

## In-App Alerts
Displayed in StatusBar until acknowledged.

---

## Email Alerts (Admins)

Subject example:
```
[FDMS CRITICAL] Certificate expired – submissions blocked
```

Email must include:
- DeviceID
- Timestamp
- Impact
- Required action

---

# 7️⃣ Backend API Endpoints

```http
GET /api/dashboard/summary
GET /api/dashboard/errors
GET /api/dashboard/quickbooks
GET /api/dashboard/export/pdf
GET /api/dashboard/export/excel
```

All endpoints are **read-only**.

---

# 8️⃣ Role-Based Visibility

### Cashier
- Today’s metrics
- Pending receipts

### Accountant
- Financial metrics
- QuickBooks panel
- Credit notes

### Admin
- All metrics
- Alerts
- Compliance snapshot

---

# 9️⃣ Non-Negotiable Rules

- Never show draft data as fiscal
- Never hide errors
- Never recompute fiscal totals
- Never allow dashboard edits

---

## Action for Cursor

1. Create dashboard APIs
2. Aggregate FDMS-confirmed metrics
3. Build React dashboard UI
4. Add time filters
5. Add tests
6. Add exports
7. Add alerts

---

## Final Rule

> If an auditor can understand the dashboard without explanation, it is correct.
