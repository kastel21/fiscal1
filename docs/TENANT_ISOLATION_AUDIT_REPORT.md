# Tenant Isolation Audit Report

**Date:** 2026-03-09  
**Scope:** Django FDMS multi-tenant fiscal invoicing platform  
**Goal:** Identify queries that could return or modify data from the wrong tenant.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH     | 14    |
| MEDIUM   | 12    |
| LOW      | 6     |

**Tenant-scoped models (this audit):**  
`FiscalDevice`, `FiscalDay`, `Receipt`, `Company`, `FDMSConfigs`, `FDMSApiLog`, `QuickBooksConnection`, `QuickBooksInvoice`, `Product`, `Customer`, `TaxMapping`, `InvoiceSequence`, `DocumentSequence`, `ActivityEvent`, `AuditEvent`, `ReceiptSubmissionResponse`, `DebitNote`, `CreditNote`, and other `TenantAwareModel` subclasses.

**Notes:**
- `QuickBooksEvent` has **no** `tenant` field (global audit log). Queries on it are inherently cross-tenant.
- Views that use `Receipt.objects.all()` then `if tenant: queryset = queryset.filter(tenant=tenant)` are **safe** but fragile; prefer starting with a tenant filter when `request.tenant` is set.
- Many issues are “when `request.tenant` is None”: unauthenticated or tenant-exempt paths can see or change another tenant’s data.

---

## 1. HIGH severity

### 1.1 Device selection without tenant (`.first()` no tenant)

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/views.py` | 33 | `FiscalDevice.all_objects.filter(is_registered=True).first()` | When no tenant: require `device_id` or refuse; when tenant: `FiscalDevice.objects.filter(tenant=request.tenant, is_registered=True).first()` | `_get_device()` no-tenant fallback returns first device globally. |
| `dashboard/context.py` | 8, 40 | `FiscalDevice.objects.filter(is_registered=True).first()` | Accept `tenant` (e.g. from request); use `FiscalDevice.objects.filter(tenant=tenant, is_registered=True).first()` when tenant set; else document as “global dashboard only”. | Used for offline status and navigation; can expose one tenant’s device as “the” device. |
| `offline/views.py` | 16 | `FiscalDevice.objects.filter(is_registered=True).first()` | Resolve tenant (e.g. `request.tenant`) and filter: `FiscalDevice.objects.filter(tenant=tenant, is_registered=True).first()`. | Same pattern. |
| `fiscal/views_health.py` | 19 | `FiscalDevice.objects.filter(is_registered=True).first()` | Same as above: scope by `request.tenant` when available. | Health check could report another tenant’s device. |

### 1.2 Company without tenant

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/views_fdms.py` | 677 | `Company.objects.first()` (when no tenant) | When tenant is None, do not show/update company, or use a dedicated “global settings” path with strict access control. | Settings page fallback. |
| `fiscal/views_fdms.py` | 698, 729 | `Company.objects.first()` | Always scope by tenant: `Company.objects.filter(tenant=request.tenant).first()`; create with `tenant=request.tenant` when creating. | Logo upload/remove affect first company in DB regardless of tenant. |

### 1.3 FiscalDevice / Receipt by id without tenant

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `device_identity/views.py` | 49, 59 | `FiscalDevice.objects.get(device_id=device_id)` | When request has tenant: `FiscalDevice.objects.filter(tenant=request.tenant, device_id=device_id).get()`; else restrict to admin or require tenant. | Device status can leak to other tenants. |
| `fiscal/views.py` | 600, 609 | `FiscalDevice.objects.get(device_id=device_id)` | Same: add `tenant=request.tenant` when tenant is set. | Device register page. |
| `fiscal/services/fiscal_service.py` | 21 | `Receipt.objects.filter(pk=receipt_id).first()` | Use `Receipt.all_objects.filter(pk=receipt_id).first()` then validate `receipt.device.tenant` for downstream; or pass `tenant_id` into task and use `Receipt.objects.filter(tenant=tenant, pk=receipt_id).first()`. | In Celery, `Receipt.objects` is tenant-filtered; with no tenant set the receipt is never found (bug). |

### 1.4 Config / device by device_id without tenant

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/views_management.py` | 39 | `FiscalDevice.all_objects.filter(device_id=did, is_registered=True).first()` | When `request.tenant` is set: `FiscalDevice.objects.filter(tenant=request.tenant, device_id=did, is_registered=True).first()`. | API config/taxes could expose another tenant’s device. |
| `fiscal/views_management.py` | 179 | `Company.objects.first()` | `Company.objects.filter(tenant=request.tenant).first()` (and ensure view is tenant-scoped). | Management view. |

### 1.5 Dashboard / metrics without tenant

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `dashboard/services/metrics_service.py` | 25, 36 | `FiscalDevice.objects.all()`, `Receipt.objects.all()` | Accept optional `tenant`; when provided use `.filter(tenant=tenant)` for both. When not provided, document as superuser/global dashboard only. | KPIs aggregate all tenants. |
| `fiscal/services/audit_integrity.py` | 225 | `FiscalDevice.objects.filter(is_registered=True)` | Run per tenant or pass tenant: `FiscalDevice.objects.filter(tenant=tenant, is_registered=True)`; or iterate tenants and run audit per tenant. | Full audit runs over all devices globally. |

---

## 2. MEDIUM severity

### 2.1 `.get(pk=...)` on tenant-scoped models (assumes middleware)

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/views_management.py` | 406, 479, 568 | `Product.objects.get(pk=pk)`, `Customer.objects.get(pk=pk)`, `TaxMapping.objects.get(pk=pk)` | Ensure URLs are always under tenant middleware; or add explicit `Product.objects.filter(tenant=request.tenant).get(pk=pk)` (and same for Customer, TaxMapping). | Safe only if `request.tenant` is always set. |
| `fiscal/forms/debit_note_form.py` | 40 | `Receipt.objects.get(pk=inv_id)` | Use `Receipt.objects.filter(tenant=request.tenant, pk=inv_id).get()` when tenant is available (e.g. from request). | Form used in tenant context; explicit tenant is safer. |
| `fiscal/forms/credit_note_form.py` | 66 | Same | Same as above. | Same. |

### 2.2 QuickBooksEvent (no tenant on model)

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/services/dashboard_service.py` | 218 | `QuickBooksEvent.objects.order_by("-created_at").first()` | Add `tenant` to `QuickBooksEvent` and filter by tenant; or filter by `realm_id` and resolve realm_id → tenant for current user only. | “Last QB event” is global; can leak presence/timing of other tenants. |
| `fiscal/views_api.py` | 205 | `QuickBooksEvent.objects.create(event_type=..., payload=body)` | Add `tenant` to model and set from `request.tenant` or from `QuickBooksConnection` when handling webhook. | New events not associated with tenant. |

### 2.3 Company fallback in invoice context

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/services/fiscal_invoice_context.py` | 193, 309, 497 | `Company.objects.all()[:10]` (logo fallback) | Use `Company.objects.filter(tenant=device.tenant)[:10]` (device is in scope). | Logo fallback could use another tenant’s company. |

### 2.4 Tasks: device lookup without tenant in query

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/tasks.py` | 74 | `FiscalDevice.all_objects.get(device_id=device_id)` | After resolving tenant: `FiscalDevice.all_objects.filter(tenant=tenant, device_id=device_id).get()` (and keep `validate_device_for_tenant`). | Validation catches wrong tenant but query should enforce it. |

### 2.5 Context processor when no tenant

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/context_processors.py` | 17–18 | `FiscalDevice.objects.filter(is_registered=True).order_by("device_id")` (when tenant is None) | When tenant is None, either return no devices or restrict to a single-tenant “legacy” mode and document. | Exposes all registered devices in dropdown when no tenant. |

### 2.6 Config service (relies on current tenant only)

| File | Line | Unsafe query | Recommended | Notes |
|------|------|--------------|-------------|--------|
| `fiscal/services/config_service.py` | 34, 54–55 | `FDMSConfigs.objects.filter(device_id=device_id).first()`, `FDMSConfigs.objects.order_by("-fetched_at").first()` | When called from tasks/views without request, accept optional `tenant` and use `FDMSConfigs.objects.filter(tenant=tenant, device_id=device_id)` (and same for “first” path). | FDMSConfigs is TenantAwareModel; when `get_current_tenant()` is None, first() returns any tenant’s config. |

---

## 3. LOW severity

### 3.1 Intentional or constrained global use

| File | Line | Query | Notes |
|------|------|--------|--------|
| `fiscal/views_api.py` | 75 | `Receipt.objects.all()` then filter by tenant if set | Safe; consider starting with `.filter(tenant=tenant)` when tenant is set for clarity. |
| `fiscal/views_fdms.py` | 289 | Same | Same. |
| `fiscal/views.py` | 458 | Same | Same. |
| `tenants/utils.py` | 36 | `Tenant.objects.filter(is_active=True).order_by("created_at").first()` | Default tenant for legacy; document. |
| `fiscal/views_management.py` | 39 | `get_latest_configs(did)` | Relies on tenant from middleware for FDMSConfigs; device from all_objects (see HIGH 1.4). |
| `quickbooks/views.py` | 203 | `QuickBooksToken.objects.filter(...).first()` | QuickBooksToken is not tenant-scoped in this codebase; ensure only used in tenant or user-scoped flows. |

### 3.2 Receipt by device (device implies tenant)

| File | Line | Query | Notes |
|------|------|--------|--------|
| `fiscal/services/credit_note_import_service.py` | 23, 55, 61 | `Receipt.objects.filter(device__device_id=...)`, `.filter(pk=inv["id"])`, `.filter(pk__in=ids)` | Callers pass `device` from tenant context; Receipt.objects is tenant-filtered when tenant is set. LOW risk. |

### 3.3 Migrations / management commands

| File | Line | Query | Notes |
|------|------|--------|--------|
| `fiscal/migrations/0039_fiscaldevice_tenant_required.py` | 12 | `Tenant.objects.filter(...).first()` | Migration; assign default tenant. OK. |
| `tenants/management/commands/assign_default_tenant.py` | 89 | `model.objects.all()` | Management command; intentional. |
| `fiscal/management/commands/audit_fiscal_integrity.py` | 27 | `FiscalDevice.objects.filter(is_registered=True)` | Consider adding `--tenant` and filtering. |
| `fiscal/management/commands/check_certificate_expiry.py` | 23 | Same | Same. |
| `fiscal/management/commands/pre_golive_check.py` | 38 | Same | Same. |

---

## 4. QuickBooks and FiscalDevice isolation checklist

- **QuickBooksConnection:** Queries in views and sync use `tenant=request.tenant` or resolve tenant from `realm_id` in webhook/task. `fetch_invoice_from_qb` uses `realm_id` only (realm is 1:1 with tenant); acceptable.
- **QuickBooksInvoice:** List/create/fiscalise paths use `tenant=request.tenant` or tenant from connection; idempotency uses `(tenant, qb_invoice_id)`.
- **QuickBooksEvent:** No tenant field; see MEDIUM 2.2.
- **FiscalDevice:** Many `.first()` and `.get(device_id=...)` without tenant; see HIGH 1.1, 1.3, 1.4.
- **FiscalDay / Receipt / FDMSApiLog:** Views that use `request.tenant` and filter are OK; dashboard/metrics and health/offline/context need tenant (see HIGH 1.5, 1.1).

---

## 5. Recommended code changes (priority order)

1. **Company in FDMS settings and logo:** Always filter and create `Company` by `request.tenant` in `fdms_settings`, `fdms_settings_company_logo`, and `fdms_settings_company_logo_remove`.
2. **Device selection:** In `dashboard/context.py`, `offline/views.py`, `fiscal/views_health.py`, and `fiscal/views.py` `_get_device`, require tenant or explicit `device_id`; never use “first registered device” globally.
3. **FiscalDevice by device_id:** In `device_identity/views.py` and `fiscal/views.py` device register, add `tenant=request.tenant` when tenant is set.
4. **fiscalise_receipt task:** Use `Receipt.all_objects.filter(pk=receipt_id).first()` (or pass tenant and filter by tenant+pk); then use `receipt.device.tenant` for downstream.
5. **Config/taxes API:** In `fiscal/views_management.py`, resolve device with `tenant=request.tenant` when tenant is set.
6. **Metrics and dashboard context:** Add optional `tenant` to `get_metrics()` and dashboard context; filter devices and receipts by tenant when provided.
7. **QuickBooksEvent:** Add `tenant` (nullable) and set it in webhook handler and in `views_api` from `request.tenant` or connection; filter “last event” by tenant in dashboard.
8. **Audit/management commands:** Add `--tenant` and scope device/receipt queries to that tenant where appropriate.

---

## 6. Optional improvements

- **TenantAwareManager:** Already in use for models inheriting `TenantAwareModel`. Ensure all tenant-scoped models use it and that tasks that need cross-tenant access use `all_objects` explicitly and document why.
- **Base pattern for views:** In views that have `request.tenant`, always start with `Model.objects.filter(tenant=request.tenant)` (or equivalent) for tenant-scoped models instead of `.all()` + conditional filter.
- **Middleware:** Ensure tenant is set for all authenticated FDMS routes so that “no tenant” paths are rare and explicitly documented (e.g. health check, global admin).
- **QuickBooksEvent:** Add `tenant` FK and backfill from `QuickBooksConnection` by `realm_id` where possible; then use tenant in all reads/writes.

---

## 7. Files not requiring changes (verified)

- **fiscal/views_api.py** (api_fdms_receipts, api_devices_list): Tenant applied when present.
- **fiscal/views_fdms.py** (fdms_receipts, fdms_settings, fdms_qb_invoices, fdms_settings_qb_disconnect): Tenant applied when present; only Company and “first device” fallbacks need fixes.
- **fiscal/views.py** (dashboard, receipt_history, fiscal_day_dashboard, fdms_logs): Same; device list and receipt list are tenant-filtered when tenant is set.
- **fiscal/services/dashboard_service.py** (get_summary, get_receipts, get_quickbooks_stub): Accepts `tenant` and filters; only QuickBooksEvent and “first device” when tenant is None need attention.
- **fiscal/tasks.py**: Uses `tenant_id`, validates device vs tenant; only device fetch should be tenant-scoped in query.
- **quickbooks/tasks.py**: Resolves tenant from `QuickBooksConnection` by `realm_id`; idempotency and fiscalise are tenant-scoped.
- **fiscal/services/qb_fiscalisation.py**, **qb_sync.py**, **qb_client.py**: Use `tenant` parameter and filter connection/device/invoice by tenant.
- **fiscal/services/qb_service.py** (handle_qb_event): Resolves tenant from connection by `realm_id`; device and receipt are tenant-scoped.

---

*End of report.*
