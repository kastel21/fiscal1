# FDMS API Reference

Reference for REST and JSON APIs exposed by the FDMS Django application.

---

## Authentication

All endpoints require staff authentication. Two modes:

1. **Session auth**: Log in via `/admin/login/`; session cookie is used.
2. **JWT auth**: `POST /api/token/` with `{"username","password"}` returns `{access, refresh}`. Send `Authorization: Bearer <access>` for API calls. Use `POST /api/token/refresh/` with `{"refresh"}` to renew.

---

## Web UI Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /fdms/dashboard/ | FDMS dashboard (Tailwind UI) |
| GET | /fdms/device/ | Device registration page |
| POST | /fdms/device/ | Register device |
| GET | /fdms/fiscal/ | Fiscal day control page |
| POST | /fdms/fiscal/open/ | Open fiscal day |
| POST | /fdms/fiscal/close/ | Close fiscal day |
| GET | /fdms/receipts/ | Receipts list |
| GET | /fdms/receipts/new/ | New receipt form |
| POST | /fdms/receipts/new/ | Submit receipt |
| GET | /fdms/receipts/<pk>/ | Receipt detail |
| GET | /fdms/logs/ | FDMS API logs |
| GET | /fdms/audit/ | Integrity audit page |
| POST | /fdms/audit/ | Run integrity audit |

---

## JSON API Endpoints (for React / external clients)

### GET /api/dashboard/metrics/

KPI metrics for real-time dashboard. Query param: device_id (optional).

**Response:**
- activeDevices, totalDevices
- receiptsToday, failedReceipts, successRate (24h)
- avgLatencyMs, queueDepth
- sales: { ZWL: N, USD: N }
- taxBreakdown: [{ band: "15%", amount: N }]
- receiptsPerHour: [{ hour, count }]

### GET /api/fdms/dashboard/

Returns dashboard data.

**Response:**
- device: deviceID, status, certExpiry
- fiscal: dayNo, status, receiptCount
- lastReceipt: globalNo, total, serverVerified

### GET /api/fdms/receipts/

Returns recent receipts. Query param: device_id (optional).

**Response:** receipts array with id, deviceId, fiscalDayNo, receiptGlobalNo, invoiceNo, receiptType, total, createdAt.

### GET /api/fdms/fiscal/

Returns fiscal day status. Query param: device_id (optional).

**Response:** dayNo, status, lastReceiptGlobalNo, error.

### GET /api/fdms/status/

Live GetStatus from FDMS. Query params: device_id, refresh (1 to force fetch).

---

## Action APIs (POST)

### POST /api/open-day/

Opens a new fiscal day. Body: {"device_id": 12345}.

**Async mode:** Add `?async=1` or header `X-Use-Celery: 1` to enqueue task and return `{status: "queued", task_id: "..."}`. Connect to WebSocket `ws/fdms/device/<device_id>/` for `fiscal.opened` events.

### POST /api/close-day/

Initiates fiscal day close. Body: {"device_id": 12345}.

**Async mode:** Add `?async=1` or header `X-Use-Celery: 1` to enqueue task and return `{status: "queued", task_id: "..."}`. Connect to WebSocket for `fiscal.closed` events.

### Management APIs (Company, Devices, Products)

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/company/ | Get company settings |
| PUT | /api/company/ | Update company settings |
| GET | /api/devices/ | List registered devices |
| GET | /api/devices/<id>/ | Device detail |
| POST | /api/devices/<id>/open-day/ | Open fiscal day |
| POST | /api/devices/<id>/close-day/ | Close fiscal day |
| GET | /api/products/ | List products (query: company_id) |
| POST | /api/products/ | Create product |
| GET | /api/products/<id>/ | Product detail |
| PUT | /api/products/<id>/ | Update product |
| DELETE | /api/products/<id>/ | Deactivate product (soft delete) |
| GET | /api/devices/<id>/certificate-status/ | Certificate expiry for widget |

### GET /api/devices/

Returns list of registered devices for invoice form.

**Response:** `{ "devices": [ { "id", "device_id", "fiscal_day_status", "last_fiscal_day_no", "certificate_valid_till" } ] }`

### POST /api/invoices/

Create and submit invoice to FDMS. Body: device_id, currency, customer_name, customer_tin, customer_address, customer_phone, customer_email, invoice_reference, notes (all optional), items (product_id, quantity, item_name), payments (method, amount). Validation: at least one item, payment total >= grand total.

**Response:** `{ "success": true, "receipt_id", "receipt_global_no", "receipt_counter" }` or `{ "error": "..." }`

### POST /api/submit-receipt/

Submits a receipt. Body: device_id, fiscal_day_no, receipt_type, receipt_currency, invoice_no, receipt_total, receipt_lines, receipt_taxes, receipt_payments, receipt_lines_tax_inclusive.

**Async mode:** Add `"async": true` in body, or `?async=1`, or header `X-Use-Celery: 1`. Returns `{status: "queued", task_id: "..."}`. Connect to WebSocket for `receipt.progress` (0–100%) and `receipt.completed` events.

**SubmitReceipt payload (FDMS v7.2):** The service builds and sends:

```json
{
  "receipt": {
    "deviceID": 42,
    "receiptType": "FISCALINVOICE",
    "receiptCurrency": "ZWL",
    "receiptGlobalNo": 125,
    "receiptDate": "2026-02-13T19:42:10",
    "receiptTotal": 400,
    "receiptLines": [
      {
        "receiptLineType": "Sale",
        "receiptLineName": "Lager Beer",
        "receiptLineQuantity": 2,
        "receiptLinePrice": 200,
        "receiptLineTotal": 400,
        "receiptLineTaxCode": "A",
        "receiptLineHSCode": "220300"
      }
    ],
    "receiptTaxes": [
      {
        "taxCode": "A",
        "taxPercent": 15.00,
        "taxAmount": 52,
        "salesAmountWithTax": 400
      }
    ],
    "receiptPayments": [
      {
        "moneyType": "CASH",
        "paymentAmount": 400
      }
    ],
    "receiptDeviceSignature": {
      "hash": "BASE64_SHA256_HASH",
      "signature": "BASE64_SIGNATURE"
    }
  }
}
```

### POST /api/re-sync/

Re-syncs device state from FDMS GetStatus. Body: {"device_id": 12345}.

---

## WebSocket (Real-time)

**URL:** `ws://<host>/ws/fdms/device/<device_id>/`

Staff authentication required. Subscribe to group `fdms_device_<device_id>` for live events.

**Events:**
- `receipt.progress` — `{percent, stage, invoice_no}` (0–100%)
- `receipt.completed` — `{receipt_global_no, fdms_receipt_id, invoice_no}`
- `fiscal.opened` — `{fiscal_day_no, status}`
- `fiscal.closed` — `{operation_id, status}`
- `activity` — `{event_type, message}`
- `error` — `{message}`

---

## Security Notes

- Private keys are never returned by any API.
- Decrypted keys are never exposed.
- Receipt deletion is not supported via API.
- Fiscal state is validated before receipt submission.
