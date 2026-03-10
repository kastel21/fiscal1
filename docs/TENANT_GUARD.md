# Tenant Guard (Stripe-Style Multi-Tenant Isolation)

This document describes the global tenant guard: **TenantAwareModel** and **TenantAwareManager**, which ensure tenant-scoped models automatically filter by the active tenant and cannot leak data across tenants.

## Overview

- **TenantAwareManager** (default `objects`): When a current tenant is set (via middleware or `set_current_tenant()`), all queries are filtered by that tenant. When no tenant is set, `.objects` returns an **empty** queryset so that forgotten filters cannot leak data.
- **all_objects**: Unscoped manager for admin, migrations, background tasks, and any code that must see or modify data across tenants. Use sparingly and only where tenant context is not available or global access is required.

## Components

### 1. TenantAwareManager (`tenants/managers.py`)

- `get_queryset()`:
  - If `get_current_tenant()` is `None` → returns `qs.none()`.
  - If current tenant is set and the model has a `tenant` attribute → returns `qs.filter(tenant=tenant)`.
- Use `Model.objects` for normal tenant-scoped access in views and services when `request.tenant` or task tenant context is set.

### 2. TenantAwareModel (`tenants/models_base.py`)

- Abstract base that adds:
  - `objects = TenantAwareManager()`
  - `all_objects = models.Manager()`
- Subclasses must define their own `tenant` ForeignKey to `tenants.Tenant` (e.g. `tenant = models.ForeignKey("tenants.Tenant", ...)`).
- Fiscal models that inherit: `Company`, `FiscalDevice`, `FiscalDay`, `Receipt`, `FDMSApiLog`, `Customer`, `Product`, `FiscalDay`, `DocumentSequenceAdjustment`, `ActivityEvent`, `AuditEvent`, `ReceiptSubmissionResponse`, `DebitNote`, `CreditNote`, and others with a tenant FK.

### 3. Current tenant context (`tenants/context.py`)

- `get_current_tenant()`: Returns the tenant for the current request/task (contextvar).
- `set_current_tenant(tenant)`: Sets the current tenant (e.g. in Celery tasks). Returns a token for reset.
- `clear_current_tenant(token)`: Restores the previous context (e.g. in a `finally` block).

Middleware sets the current tenant when resolving the request; background tasks must call `set_current_tenant(device.tenant)` (or similar) after loading the tenant-scoped entity if they then use `Model.objects`.

## How to query tenant models

### In views (tenant set by middleware)

- Use **`Model.objects`** as usual. The middleware has set `request.tenant` and `set_current_tenant(tenant)`, so `Model.objects.filter(...)` is automatically scoped to that tenant.

### In background tasks

1. Load the tenant-scoped entity with **`Model.all_objects`** (e.g. `FiscalDevice.all_objects.get(device_id=...)`).
2. Call **`set_current_tenant(device.tenant)`** (or the appropriate tenant).
3. Run the rest of the task (e.g. `Receipt.objects`, `submit_receipt(...)`); they will be tenant-scoped.
4. In a **`finally`** block, call **`clear_current_tenant(token)`**.

Example (see `fiscal/tasks.py`):

```python
device = FiscalDevice.all_objects.get(device_id=device_id)
token = None
if device.tenant_id:
    token = set_current_tenant(device.tenant)
try:
    # ... use Receipt.objects, etc.
finally:
    if token is not None:
        clear_current_tenant(token)
```

### In admin

- **TenantAdminMixin** uses **`Model.all_objects`** when building the queryset so superadmin sees all tenants. When `request.tenant` is set (e.g. API with header), the mixin filters by that tenant.

### In management commands / scripts

- No request context: **`get_current_tenant()`** is `None`, so **`Model.objects`** would return nothing. Use **`Model.all_objects`** when you need to read or write tenant-scoped data, and filter by `tenant=...` explicitly if required.

### When to use `all_objects`

Use **`Model.all_objects`** only when:

- Running in a context where no tenant is set (Celery task start, management command, cron).
- You need to load an entity by id/device_id and then set tenant context for the rest of the flow.
- Admin/superadmin must see or edit data across all tenants.
- Migrations or one-off scripts that operate on all tenants.

Do **not** use `all_objects` in normal request-handling code when tenant is set; use `Model.objects` so the guard remains in effect.

## Middleware and performance

- **Tenant cache**: For non-superuser users, allowed tenant IDs are cached on **`request.user._tenant_cache`** (a set) once per request. **`user_has_tenant_access(user, tenant)`** uses this cache when present to avoid repeated `user.tenants.filter(...)` queries.
- **Internal API**: When `TENANT_HEADER_FOR_INTERNAL_API` is True, the **`X-Internal-Client`** header must match **`INTERNAL_API_TOKEN`** (env or settings). If the header is present and the token does not match, the request receives 403.

## Fiscal device guard

- **`validate_device_for_tenant(device, tenant)`** (in `fiscal.utils`) ensures a device belongs to the given tenant. Use it wherever a device is used for receipts or fiscal operations (views, tasks, invoice creation). Tasks that accept `tenant_id` validate the device before running; they also set tenant context via **`set_current_tenant(device.tenant)`** so subsequent **`Model.objects`** usage is correct.

## Tests

- Tests that create tenant-scoped data without setting tenant context should use **`Model.all_objects.create(...)`** so that the created rows exist. Tests that assert tenant isolation can set **`set_current_tenant(tenant)`** and then use **`Model.objects`** to verify only that tenant’s data is visible.
- **TenantAwareManagerTests** in **`tenants/tests.py`** verify: no tenant → empty `objects`; tenant set → `objects` filtered; **`all_objects`** always sees all rows; **`user_has_tenant_access`** respects **`_tenant_cache`**.

## Summary

| Context              | Use           | Notes                                              |
|----------------------|---------------|----------------------------------------------------|
| View (tenant set)    | `Model.objects` | Automatically scoped by middleware                 |
| Celery task          | `all_objects` to load; then `set_current_tenant`; then `Model.objects` | Clear tenant in `finally` |
| Admin                | `all_objects` in TenantAdminMixin                   | So superadmin sees all                             |
| Management command  | `Model.all_objects` (+ filter by tenant if needed)  | No request context                                  |
| Tests (setup/assert) | `all_objects` for creates/global access            | Use `set_current_tenant` to test tenant filtering   |
