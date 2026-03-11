# Fiscal Compliance Audit Report — Django FDMS / ZIMRA

**Project:** Multi-tenant fiscal invoicing system (ZIMRA FDMS)  
**Audit date:** 2025-03-09  
**Scope:** Fiscal device integrity, fiscal day lifecycle, receipt flow, identity fields, hash chain, API error handling, logging, QR verification, tenant isolation, background tasks, environment safety.

---

## Executive summary

The system implements a solid fiscal flow: device–tenant validation, OpenDay/CloseDay with status checks, receipt submission with fiscal-day gating, receipt-level hash chain (`previousReceiptHash`), FDMS response persistence, retries, and tenant-scoped views. Several gaps remain: **Tenant.previous_hash** is never updated; **FiscalDay** and **ReceiptSubmissionResponse** are created without tenant; **dashboard Excel export** is not tenant-scoped; and **FiscalDevice.tenant** is nullable, allowing devices without a tenant.

---

## 1. Fiscal device integrity

### 1.1 Device–tenant linkage

| Finding | Severity | Location | Details |
|--------|----------|----------|---------|
| **FiscalDevice.tenant is nullable** | **MEDIUM** | `fiscal/models.py` (lines 41–47) | `tenant = models.ForeignKey(..., null=True, blank=True)`. A device can exist without a tenant; the app enforces tenant via `validate_device_for_tenant()` but the schema does not require one device per tenant. |
| **device_id is globally unique** | OK | `fiscal/models.py` (line 55) | `device_id = models.IntegerField(unique=True)` — one device_id in the system. |
| **Device–tenant guard in use** | OK | `fiscal/utils/__init__.py`, views, tasks | `validate_device_for_tenant(device, tenant)` is used in views, management API, and tasks (when `tenant_id` is passed). |

**Recommendation:** For strict multi-tenant compliance, consider making `FiscalDevice.tenant` non-nullable and migrating existing rows to a default tenant, or add a DB constraint that at least one of tenant or a “global” flag is set.

### 1.2 Credentials and cross-tenant use

- **Credentials:** Stored per device: `certificate_pem`, `private_key_pem`, `device_serial_no` on `FiscalDevice` (`fiscal/models.py`). No cross-tenant use when validation is applied.
- **Cross-tenant use:** Prevented by tenant-scoped device resolution and `validate_device_for_tenant()` in receipt submission, open/close day, management APIs, and invoice creation.

---

## 2. Fiscal day lifecycle

### 2.1 OpenDay / CloseDay locations

| Component | File | Notes |
|-----------|------|--------|
| OpenDay API | `fiscal/services/device_api.py` (lines 159–251) | `open_day(device)` — GetStatus, then OpenDay if `FiscalDayClosed` |
| CloseDay API | `fiscal/services/device_api.py` (lines 337–410) | `close_day(device)` — GetStatus, then CloseDay if `FiscalDayOpened` or `FiscalDayCloseFailed` |
| Views | `fiscal/views.py` (open_day_api, close_day_api), `fiscal/views_fdms.py` (fdms_open_day_post, fdms_close_day_post), `fiscal/views_management.py` (api_device_open_day, api_device_close_day) | All use device from request; tenant validation in management views. |
| Tasks | `fiscal/tasks.py` (open_day_task, close_day_task) | Optional `tenant_id`; validate device for tenant when provided. |

### 2.2 One open day per device

- **Enforced:** `device_api.open_day()` calls GetStatus and only proceeds if `fiscalDayStatus == "FiscalDayClosed"` (lines 173–175). FDMS effectively allows only one open day per device.
- **Local state:** `FiscalDay` has `unique_together = [["device", "fiscal_day_no"]]`; device has `last_fiscal_day_no` and `fiscal_day_status` updated on OpenDay/CloseDay/GetStatus.

### 2.3 Receipts only when day is open

- **Enforced:** `receipt_service._do_submit_receipt()` checks `status in ("FiscalDayOpened", "FiscalDayCloseFailed")` (lines 661–663). Otherwise returns: *"Cannot submit: status must be FiscalDayOpened or FiscalDayCloseFailed"*.

### 2.4 Close day and state updates

- **device_api.close_day():** Builds payload from receipts and fiscal day, signs, POSTs CloseDay; does not poll. Caller must poll GetStatus.
- **fdms_device_service.update_device_status():** On GetStatus response, updates `device.last_fiscal_day_no`, `last_receipt_global_no`, `fiscal_day_status`; for `FiscalDayClosed` updates `FiscalDay` record with `closed_at` and clears `closing_error_code`; for `FiscalDayCloseFailed` updates last FiscalDay with `closing_error_code`.

### 2.5 FiscalDay created without tenant

| Finding | Severity | Location | Details |
|--------|----------|----------|---------|
| **FiscalDay created without tenant** | **LOW** | `fiscal/services/device_api.py` (lines 236–242) | `FiscalDay.objects.create(device=device, fiscal_day_no=..., status=..., opened_at=..., closed_at=None)` — no `tenant` set. FiscalDay has `tenant` FK (null=True). Tenant-scoped dashboards filter by device (which may have tenant); listing by tenant is still possible via device.tenant. |

**Recommendation:** Set `tenant_id=device.tenant_id` when creating `FiscalDay` so tenant-scoped queries and reporting are consistent.

---

## 3. Receipt issuance flow

Flow is implemented as specified:

1. **Validate device** — View/task resolves device; when tenant is set, device is tenant-scoped and `validate_device_for_tenant(device, tenant)` is called.
2. **Confirm fiscal day open** — `_do_submit_receipt()` checks `fiscalDayStatus` in (`FiscalDayOpened`, `FiscalDayCloseFailed`) (receipt_service.py 661–663).
3. **Build receipt payload** — Canonical string, previous receipt hash, device signature, receipt lines/taxes/payments (receipt_service.py ~726–1024).
4. **Send to FDMS** — `FDMSDeviceService().device_request("POST", path, body=body, device=device)` (receipt_service.py 1035–1036).
5. **Save receipt response** — On 200, `Receipt.objects.update_or_create(device, receipt_global_no, defaults=...)` with `fdms_receipt_id`, `receipt_hash`, `receipt_signature_*`, `server_date`, etc. (receipt_service.py 1153–1165).
6. **Store fiscal signature** — `apply_fdms_response_to_receipt(receipt_obj, data)` sets `fiscal_signature`, `verification_code`, VAT breakdown (fdms_response_mapper.py). Receipt already has `receipt_hash` / `receipt_signature_*` from submit flow.

**Idempotency:** First receipt of day uses GetStatus for `lastReceiptGlobalNo`; subsequent use `device.last_receipt_global_no + 1`. Duplicate `receipt_global_no` and duplicate (device, fiscal_day_no, invoice_no) with existing `fdms_receipt_id` return existing receipt.

---

## 4. Receipt identity fields

| Field | Source | Persisted |
|-------|--------|-----------|
| **ReceiptGlobalNumber** | Request + FDMS response | `receipt_global_no` (Receipt); also in ReceiptSubmissionResponse |
| **FiscalSignature** | FDMS response / receiptDeviceSignature hash | `fiscal_signature`, `receipt_hash`, `receipt_signature_hash`, `receipt_signature_sig` |
| **FiscalDayNumber** | Request + response | `fiscal_day_no` |
| **DeviceID** | device FK | `device` (Receipt.device_id) |
| **Timestamp** | FDMS serverDate / receipt_date | `server_date`, `receipt_date`, `created_at` |

All values come from FDMS or the validated request and are stored in `Receipt` (and in submission response where applicable). Section 10 fields (fiscal_invoice_number, receipt_number, verification_code, VAT breakdown, buyer) are applied via `apply_fdms_response_to_receipt()`.

---

## 5. Hash chain / previous hash

### 5.1 Receipt-level chain (implemented)

- **previousReceiptHash:** Last receipt’s `receipt_hash` is taken from the last receipt in the same (device, fiscal_day_no) (receipt_service.py 730–746). Passed in payload as `previousReceiptHash` (1019–1020). Canonical string includes it (receipt_engine.py 106–107).
- **Integrity:** Local chain is validated (e.g. `last_receipt.receipt_global_no` vs FDMS `lastReceiptGlobalNo`) before submit (737–742). Audit/verification in `audit_integrity.py` (verify_receipt_signature, chain checks).

### 5.2 Tenant.previous_hash (not used)

| Finding | Severity | Location | Details |
|--------|----------|----------|---------|
| **Tenant.previous_hash never updated** | **MEDIUM** | `tenants/models.py` (line 62) | Field exists but is never written in receipt or close-day flow. Receipt hash chain is per device/day via last receipt’s `receipt_hash`, not via Tenant.previous_hash. If ZIMRA or internal policy expects a tenant-level chain, it is missing. |

**Recommendation:** If a tenant-level chain is required, update `Tenant.previous_hash` after each successful receipt (e.g. to the new receipt’s hash) and/or after CloseDay, and ensure it is included in any required reporting. Otherwise document that chain is device/day-level only.

---

## 6. API error handling

### 6.1 Retries

- **http_client.py:** `fdms_request()` uses a session with `Retry(status_forcelist=(500, 502))` and up to `MAX_NETWORK_RETRIES + 1` attempts for `ConnectionError`/`Timeout` with backoff (lines 55–83). Does not retry 400/401/422.
- **receipt_service.submit_receipt():** Wraps `_do_submit_receipt` in a loop with `MAX_SUBMIT_RETRIES`; retries on network-like errors (lines 467–516).

### 6.2 FDMS error logging

- **log_fdms_call()** (fdms_logger.py): Used by device_api, fdms_device_service, device_registration. Logs endpoint, method, request_payload (masked), response_payload (masked), status_code, error_message, operation_id, tenant. All FDMS calls that go through these services are logged.
- **device_api / fdms_device_service:** On non-200, error body is parsed and returned; log_fdms_call records the response and errors.

### 6.3 Failed receipts and local state

- **No partial commit on failure:** Receipt is created/updated only after successful FDMS 200, inside a `transaction.atomic()` block with `select_for_update()` on the device (receipt_service.py 1153–1165). On FDMS error, only `ReceiptSubmissionResponse` may be stored (failed attempt); no Receipt with fdms_receipt_id is created.
- **ReceiptSubmissionResponse:** Stores each attempt (success or failure) for display of validation errors; does not alter receipt state.

---

## 7. FDMS API logging (FDMSApiLog)

| Field | Captured |
|-------|----------|
| Request payload | Yes (masked via mask_sensitive_fields) |
| Response payload | Yes (masked) |
| Endpoint | Yes |
| Timestamp | Yes (`created_at` auto) |
| Tenant/device context | Tenant when passed (e.g. from device.tenant); no device_id column (device inferred from endpoint path or request). |

**Gap:** `ReceiptSubmissionResponse` is created without `tenant` (receipt_submission_response_service.py 85–93). Model has `tenant` FK; setting it from `device.tenant_id` would improve tenant-scoped reporting.

---

## 8. QR code verification

- **qr_generator.py:** `_get_zimra_qr_url()` returns `settings.ZIMRA_QR_URL` or default `"https://fdms.zimra.co.zw"` (lines 15–17). QR string format: `{base_url}/{device_id(10)}{receiptDate(ddMMyyyy)}{receiptGlobalNo(10)}{receiptQrData(16)}` (line 46). Verification link includes device ID, receipt date, global number, and signature-derived data (receipt_device_signature_hash_hex → MD5 → 16 chars).

**Compliant:** QR points to the ZIMRA verification portal and includes receipt identifiers.

---

## 9. Tenant isolation

### 9.1 Receipt queries

- **Views:** Receipt list/detail views in `views_fdms.py`, `views_api.py`, `views.py` filter by `tenant=request.tenant` when `request.tenant` is set (e.g. fdms_receipts, fdms_receipt_invoice*, api_fdms_receipts, api_qb_validate_invoice_update).
- **Dashboard service:** `get_summary()`, `get_receipts()`, `get_errors()` accept `tenant` and filter devices and Receipt/FDMSApiLog by tenant.

### 9.2 Devices and logs

- Devices: Resolved tenant-scoped in views (e.g. `FiscalDevice.objects.filter(tenant=request.tenant, ...)` where tenant is set); management APIs validate device against `request.tenant`.
- Logs: FDMSApiLog filtered by tenant in dashboard, fdms_logs, fdms_logs_tailwind when tenant is set. Log entries created with `tenant=getattr(device, "tenant", None)` where device is available.

### 9.3 Export Excel not tenant-scoped

| Finding | Severity | Location | Details |
|--------|----------|----------|---------|
| **Dashboard Excel export ignores tenant** | **HIGH** | `fiscal/export_utils.py` (lines 76–110), `fiscal/views_dashboard.py` (133–142) | `render_excel(range_key)` calls `get_summary(None, range_key)` (no tenant). Invoices and credit notes sheets use `Receipt.objects.filter(...)` with no tenant filter. Errors sheet uses `get_errors(None, range_key)` (no tenant). A tenant user could export data from all tenants if the export URL is reachable without tenant context. |

**Recommendation:** Pass `request.tenant` from `api_dashboard_export_excel` into `render_excel(range_key, tenant=request.tenant)` and have `get_summary`, `get_errors`, and the Receipt querysets in `render_excel` filter by tenant when provided.

---

## 10. Background tasks

- **tasks.py:** `submit_receipt_task`, `open_day_task`, `close_day_task` accept optional `tenant_id`. When `tenant_id` is provided, they load the tenant and call `validate_device_for_tenant(device, tenant)`; on mismatch they return `{"success": False, "error": "..."}` and log a warning. Device is loaded by `device_id` only; validation ensures it belongs to the given tenant.
- **Callers:** Views that enqueue these tasks pass `tenant_id=str(tenant.id)` when `request.tenant` is set.
- **Gap:** If a task is invoked without `tenant_id` (e.g. legacy or external caller), no device–tenant check is performed — device could be used out of tenant context.

**Recommendation:** In multi-tenant deployments, require `tenant_id` for receipt/open/close tasks (e.g. reject or infer from device.tenant_id when possible).

---

## 11. Environment safety

- **Base URL:** `FDMS_BASE_URL` from `os.environ.get("FDMS_BASE_URL")` in settings (fdms_project/settings.py). Default when unset: `https://fdmsapi.zimra.co.zw`. Production (settings_production.py) requires `FDMS_BASE_URL` to be set.
- **Usage:** All FDMS calls use `getattr(settings, "FDMS_BASE_URL", "").rstrip("/")` in device_api, fdms_device_service, device_registration. No test URL; production base `https://fdmsapi.zimra.co.zw` only.

---

## 12. Additional risks and recommendations

### 12.1 Race conditions

- **Receipt global number:** Device is locked with `select_for_update()` before `update_or_create` and update of `device.last_receipt_global_no` (receipt_service.py 1153–1165). Concurrency for the same device is serialized; risk of duplicate receipt_global_no from concurrent requests is low.
- **OpenDay:** GetStatus then OpenDay is not atomic with other processes; FDMS is the source of truth. Acceptable.

### 12.2 Device misuse

- Mitigated by tenant-scoped device resolution and `validate_device_for_tenant` at submission, open/close, management API, and invoice creation. Remaining risk: tasks called without `tenant_id` and any code path that resolves device by id only without tenant (e.g. some admin or internal scripts).

### 12.3 Receipt state handling

- Draft vs fiscalised: Determined by `fdms_receipt_id` (non-null and non-zero). Failed submissions do not create a Receipt with fdms_receipt_id; only ReceiptSubmissionResponse records the attempt. Correct.

### 12.4 ZIMRA production submission

- **Certificate and config:** GetConfig and certificate validity are enforced (e.g. config freshness before submit). Expired certificate should block submission if checks are applied at submission entry points.
- **Network/timeouts:** Retries and offline queue (create_and_queue_offline_receipt) reduce risk of lost receipts due to transient failures.
- **Validation errors:** FDMS validation errors are stored in ReceiptSubmissionResponse and can be shown to the user; no silent overwrite of receipt state.

---

## Summary table: issues by severity

| Severity | Count | Items |
|----------|-------|--------|
| **HIGH** | 1 | Dashboard Excel export not tenant-scoped (data leakage risk). |
| **MEDIUM** | 2 | FiscalDevice.tenant nullable; Tenant.previous_hash never updated. |
| **LOW** | 2 | FiscalDay created without tenant; ReceiptSubmissionResponse created without tenant; tasks without tenant_id skip device–tenant check. |

---

## File reference (key paths)

- **Models:** `fiscal/models.py` (FiscalDevice, FiscalDay, Receipt, FDMSApiLog)
- **Tenant:** `tenants/models.py` (Tenant.previous_hash)
- **Device–tenant validation:** `fiscal/utils/__init__.py` (validate_device_for_tenant)
- **Fiscal day API:** `fiscal/services/device_api.py` (open_day, close_day)
- **Receipt submit:** `fiscal/services/receipt_service.py` (_do_submit_receipt, submit_receipt)
- **FDMS device/service:** `fiscal/services/fdms_device_service.py`, `fiscal/services/http_client.py`
- **Logging:** `fiscal/services/fdms_logger.py`
- **QR:** `fiscal/services/qr_generator.py`
- **Tasks:** `fiscal/tasks.py`
- **Settings/URL:** `fdms_project/settings.py`, `fdms_project/settings_production.py`
- **Export:** `fiscal/export_utils.py`, `fiscal/views_dashboard.py`
