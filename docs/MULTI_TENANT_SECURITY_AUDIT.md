# Multi-Tenant Security Audit Report

**Project:** FDMS (Fiscal Day Management System)  
**Scope:** Tenant model, middleware, tenant resolution, and user–tenant relationship  
**Date:** 2025-03-09

---

## 1. Tenant Model and User Relationship

**File:** `tenants/models.py`

| Finding | Details |
|--------|---------|
| **User relationship** | **None.** The `Tenant` model has **no** ForeignKey or ManyToMany to Django’s User model (or any user model). |
| **Fields** | `id` (UUID), `name`, `slug`, `device_id`, `device_model`, `serial_number`, key paths, `current_fiscal_day`, `previous_hash`, `is_active`, timestamps. |
| **Conclusion** | Tenants and users are not linked in the schema. Access to a tenant is not constrained by the authenticated user. |

---

## 2. How the Active Tenant Is Determined

**File:** `tenants/middleware.py` — `TenantResolutionMiddleware`

The active tenant is determined **only** by:

1. **Request header**  
   - `X-Tenant-Slug` (read from `request.META["HTTP_X_TENANT_SLUG"]` or `request.headers.get("X-Tenant-Slug")`).  
   - Header takes precedence.

2. **Session**  
   - `request.session["tenant_slug"]` (set by the select-tenant page on POST).

**Validation performed by middleware:**

- The slug is validated only in the sense that it must match an existing, **active** tenant:  
  `Tenant.objects.get(slug=slug, is_active=True)`.
- There is **no** check that the current authenticated user (`request.user`) is allowed to access that tenant.

**Exempt paths** (no tenant required; `request.tenant` remains `None`):

- `/admin/`
- `/select-tenant/`
- `/static/`, `/media/`
- `/health/`, `/api/health/`

All other paths (including `/api/devices/`, `/api/invoices/`, `/fdms/`, etc.) require a tenant; otherwise in DEBUG the user is redirected to `/select-tenant/`, and in production `Http404` is raised.

---

## 3. Validation of User vs Tenant

**Finding:** The middleware does **not** perform any validation to ensure the authenticated user is allowed to access the resolved tenant.

- There is no use of `request.user` in `tenants/middleware.py`.
- No decorator or mixin in the codebase enforces “user X may only access tenant Y.”
- Views and APIs that use `request.tenant` only **scope queries** by that tenant; they do not check whether the user is permitted to see that tenant.

---

## 4. Locations Where Tenant Context Is Used

### 4.1 Where tenant is **resolved** (set on the request)

| Location | Description |
|----------|-------------|
| `tenants/middleware.py` | **Only** place that sets `request.tenant` (from header or session). |
| `tenants/context.py` | `set_current_tenant(tenant)` is called from middleware to set thread/context-local tenant for the request. |

### 4.2 Where `request.tenant` or `getattr(request, "tenant", None)` is used (query scoping)

| File | Usage |
|------|--------|
| `fiscal/views.py` | `get_device_for_request`, dashboard, receipt history, fiscal day dashboard, FDMS logs — filter devices/logs/receipts by `request.tenant`. |
| `fiscal/views_fdms.py` | Fiscal day page, receipts list, PDF download, receipt detail, FDMS logs — filter by `request.tenant`. |
| `fiscal/views_api.py` | `api_devices_list`, `api_fdms_receipts`, dashboard APIs — filter by `request.tenant`. |
| `fiscal/views_dashboard.py` | Dashboard summary, errors, quickbooks, export — filter by `request.tenant`. |
| `fiscal/views_invoice_import.py` | Import view — filter by `request.tenant`. |
| `fiscal/context_processors.py` | FDMS device list for templates — scope by `request.tenant`. |
| `fiscal/admin_mixins.py` | Admin queryset — when `request.tenant` is set, filter by it. |

### 4.3 Where `tenant_slug` is used

| Location | Description |
|----------|-------------|
| `tenants/views.py` | `select_tenant`: reads `request.POST.get("tenant_slug")` and `request.session.get("tenant_slug")`; writes `request.session["tenant_slug"] = tenant.slug` on POST. |
| `tenants/middleware.py` | Reads `request.session.get("tenant_slug")` when header is not present. |
| `tenants/management/commands/create_fly_tenants.py` | Creates tenants with slugs `fly1`, `fly2` (no link to users in DB). |

### 4.4 Where `X-Tenant-Slug` / `HTTP_X_TENANT_SLUG` is used

| Location | Description |
|----------|-------------|
| `tenants/middleware.py` | **Only** place that reads the header to resolve tenant. |

### 4.5 Services / tasks (tenant from context or model)

- `fiscal/services/receipt_service.py` — uses `device.tenant_id` / default tenant.
- `fiscal/services/fdms_logger.py` — accepts `tenant=` for API log records.
- `fiscal/services/device_api.py`, `fdms_device_service.py` — pass `tenant` from device for logging.
- `fiscal/tasks.py` — uses tenant from DB (e.g. by `tenant_id`); `tenant_slug` in return payloads.
- `fiscal/services/ping_service.py` — logs `tenant_id`, `tenant_slug`.
- `fiscal/admin_mixins.py` — filters admin queryset by `request.tenant` when set.

---

## 5. Views/Services Enforcing User–Tenant Relationship

**Finding:** **None.** No view or service checks that `request.user` is allowed to access `request.tenant`.

- Views use `@staff_member_required` (or equivalent) for authentication/authorization.
- Authorization is “user is staff/superuser/group,” not “user may access this tenant.”
- Any staff user can access any tenant’s data by controlling the header or session.

---

## 6. Can a User Access Another Tenant by Modifying Header or Session?

| Vector | Possible? | Notes |
|--------|-----------|--------|
| **Set `X-Tenant-Slug`** (e.g. in browser DevTools or API client) | **Yes** | Middleware trusts the header and resolves tenant by slug. No user–tenant check. |
| **Set `request.session["tenant_slug"]`** | **Yes** | e.g. POST to `/select-tenant/` with `tenant_slug=other_tenant` (no check that user is allowed that tenant). Session then used on next request if header absent. |
| **Direct API calls** | **Yes** | Sending `X-Tenant-Slug: other` with valid auth (e.g. JWT) returns that tenant’s devices, receipts, etc. |

**Conclusion:** A user who can authenticate (e.g. any staff user, or any user with a valid JWT for the API) can access **any** active tenant’s data by setting the tenant slug via header or session. Tenant isolation is **data-scoping only** (queries filter by `request.tenant`); it is **not** access control.

---

## 7. Summary Table

| Question | Answer |
|----------|--------|
| Is tenant isolation enforced (data scoping)? | **Yes** — views and APIs filter by `request.tenant` so only that tenant’s rows are read. |
| Is tenant **access control** enforced (user allowed for this tenant)? | **No** — any authenticated user with tenant in header/session can access that tenant. |
| Where is tenant resolved? | **Only** in `tenants/middleware.TenantResolutionMiddleware` (header then session). |
| Where should tenant permissions be checked? | **Middleware** (after auth + tenant resolution) and/or **select_tenant** view (when setting session). Optionally a decorator on tenant-scoped views. |

---

## 8. Recommendations: Secure User–Tenant Relationship

### 8.1 Model Choice

- **Option A — Many users per tenant (recommended):**  
  Add a **ManyToMany** from User to Tenant (e.g. `User.tenants` or a through model `UserTenant` with optional role).  
  A user can then belong to multiple tenants (e.g. accountant for several companies).

- **Option B — One tenant per user:**  
  Add a **ForeignKey** on User: `tenant = models.ForeignKey(Tenant, null=True, on_delete=...)`.  
  Simpler, but each user belongs to at most one tenant.

Recommendation: **ManyToMany** (or a through model) for flexibility (e.g. roles per tenant, multiple tenants per user).

### 8.2 Where to Enforce

1. **Middleware (recommended)**  
   After `TenantResolutionMiddleware` (or inside it, after resolving tenant):
   - If `request.tenant` is set and `request.user.is_authenticated`:
     - Check that the user is allowed to access `request.tenant` (e.g. `request.tenant in request.user.tenants.all()` or equivalent).
   - If not allowed: return **403 Forbidden** (and do not run the view).
   - Optional: superusers can be allowed to access any tenant.

2. **Select-tenant view**  
   In `tenants/views.select_tenant`, when handling POST:
   - Before setting `request.session["tenant_slug"] = tenant.slug`, verify that `request.user.is_authenticated` and that the user is allowed to access `tenant` (e.g. `tenant in request.user.tenants.all()`).
   - If not allowed: do not set session; return an error or redirect with a message.

3. **Optional: decorator**  
   A decorator (e.g. `@require_tenant_access`) on views that use `request.tenant` can redundantly check user–tenant; middleware is still recommended as the single enforcement point so no view is missed.

### 8.3 Implementation Sketch

1. **Migration**
   - Add a M2M (or through model) linking User to Tenant (e.g. `User.tenants` or `UserTenant(user, tenant, role)`).
   - Backfill: e.g. assign existing users to tenants (e.g. by convention like `create_fly_tenants`: user `fly1` → tenant `fly1`) or run a data migration.

2. **Middleware**
   - After resolving `request.tenant` from header/session:
     - If `request.tenant` is None: proceed (exempt or no tenant).
     - If `request.tenant` is set and request is authenticated:
       - If user has no tenant relation: optionally allow only if superuser, else 403.
       - Else: allow only if `request.tenant` is in the user’s tenants (or user is superuser); else 403.

3. **Select-tenant**
   - Require login (e.g. `@login_required`).
   - On POST: only list/set tenants that the user is allowed to access; when setting `session["tenant_slug"]`, verify again that the chosen tenant is in the user’s tenants.

4. **Admin / API**
   - Keep using `request.tenant` for query scoping; add the same “user may access this tenant” check in middleware so API and HTML views are protected uniformly.

This gives a clear, single place (middleware) where tenant access is validated, with optional hardening in the select-tenant view and in decorators if desired.
