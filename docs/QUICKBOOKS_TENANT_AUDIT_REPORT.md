# QuickBooks Online Integration — Tenant Isolation Audit Report

**Date:** 2025-03-10  
**Scope:** Multi-tenant FDMS application — storage and use of QuickBooks OAuth2 credentials (realm_id, access_token, refresh_token) and API usage.  
**Goal:** Verify credentials are stored per tenant and API calls use the correct tenant context.

---

## Executive Summary

**Finding: QuickBooks credentials are not isolated per tenant.** The application uses two separate credential stores, neither of which is linked to the `Tenant` model. All connection lookups use global or realm-based queries (e.g. “first active connection” or “by realm_id only”). There is no relationship between a tenant and a QuickBooks connection, and no guarantee that the correct tenant’s credentials are used for API calls. **This is a cross-tenant security risk.**

---

## 1. QuickBooks Integration Code Locations

| Area | Path | Purpose |
|------|------|---------|
| **fiscal app (primary)** | `fiscal/models.py` | `QuickBooksConnection`, `QuickBooksInvoice`, `QuickBooksEvent` |
| | `fiscal/services/qb_oauth.py` | OAuth authorize URL, code exchange, token refresh (uses `QuickBooksConnection`) |
| | `fiscal/services/qb_client.py` | QB API client (python-quickbooks), fetch invoices/sales receipts |
| | `fiscal/services/qb_sync.py` | Sync from QB → fiscalise |
| | `fiscal/services/qb_fiscalisation.py` | Map QB invoice → FDMS receipt, submit |
| | `fiscal/services/qb_service.py` | Webhook verify, fetch invoice from QB API (token + legacy) |
| | `fiscal/views_api.py` | OAuth connect/callback, webhook, sync, retry, invoice list |
| | `fiscal/views_fdms.py` | Settings QB block, disconnect, QB invoices page |
| | `fiscal/views_dashboard.py` | Dashboard QuickBooks stub API |
| | `fiscal/services/dashboard_service.py` | `get_quickbooks_stub()` |
| **quickbooks app** | `quickbooks/models.py` | `QuickBooksToken`, `QuickBooksAPILog`, `QuickBooksWebhookEvent` |
| | `quickbooks/services.py` | OAuth code exchange (tokens), revoke, query/pull/fetch/update invoice |
| | `quickbooks/views.py` | OAuth connect/callback (qb/), webhook, disconnect, pull, push |
| | `quickbooks/utils.py` | Token refresh, `get_valid_token(realm_id, user)`, webhook verify |
| | `quickbooks/client.py` | `QuickBooksClient(realm_id, user)` — API requests |
| **Settings** | `fdms_project/settings.py` | `QB_*`, `QUICKBOOKS_*` (client secrets + **global** realm/token) |
| **URLs** | `fiscal/urls.py`, `fdms_project/urls.py` | `/api/integrations/quickbooks/*`, `/qb/*` |

---

## 2. Models Used to Store QuickBooks Credentials

### 2.1 `fiscal.models.QuickBooksConnection`

**File:** `fiscal/models.py` (lines 669–684)

```python
class QuickBooksConnection(models.Model):
    """OAuth 2.0 connection to QuickBooks Online. One active connection per realm."""

    realm_id = models.CharField(max_length=50, unique=True, db_index=True)
    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

- **Tenant linkage:** **None.** No `ForeignKey` (or similar) to `tenants.Tenant`.
- **Fields:** `realm_id`, `access_token_encrypted`, `refresh_token_encrypted`, `token_expires_at`, `company_name`, `is_active`.
- **Uniqueness:** `realm_id` is unique (one DB row per QB company/realm), not per tenant.

### 2.2 `quickbooks.models.QuickBooksToken`

**File:** `quickbooks/models.py` (lines 13–72)

```python
class QuickBooksToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        ...
    )
    realm_id = models.CharField(max_length=64, db_index=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    ...
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
```

- **Tenant linkage:** **None.** Only optional `user` FK; no `tenant` FK.
- **Fields:** `realm_id`, `access_token`, `refresh_token`, `expires_at`, etc.
- **Lookup:** By `realm_id` (+ optional `user`). No tenant in key.

---

## 3. Tenant Linkage Verification

**Expected (per-tenant) pattern:**

```python
tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE)
# or
tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, ...)
```

**Actual:**

- **QuickBooksConnection:** No `tenant` field. **Security risk:** credentials are global per `realm_id`, not per tenant.
- **QuickBooksToken:** No `tenant` field. **Security risk:** tokens are keyed by `realm_id` (and optionally user), not tenant.

Neither model can enforce “this connection/token belongs to this tenant.”

---

## 4. OAuth Callback Handling

### 4.1 Fiscal app callback (used by FDMS UI)

**File:** `fiscal/views_api.py` (lines 337–349)

```python
@staff_member_required
def api_qb_oauth_callback(request):
    ...
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    ...
    data, err = exchange_code_for_tokens(code, redirect_uri, realm_id)
```

**File:** `fiscal/services/qb_oauth.py` (lines 92–99)

```python
conn, _ = QuickBooksConnection.objects.update_or_create(
    realm_id=realm_id,
    defaults={
        "access_token_encrypted": encrypt_string(access),
        "refresh_token_encrypted": encrypt_string(refresh),
        "token_expires_at": expires_at,
        "is_active": True,
    },
)
```

- **Tenant determination:** **None.** Callback does not use `request.tenant`, `request.session["tenant_slug"]`, or OAuth `state` to bind the connection to a tenant.
- **Stored data:** `realmId`, `access_token`, `refresh_token` (and expiry) are saved only by `realm_id`. Any staff user completing OAuth overwrites/creates the same global record for that realm.

### 4.2 QuickBooks app callback (`/qb/callback/`)

**File:** `quickbooks/views.py` (lines 152–170)

- Uses `realm_id` from `request.GET` and optional `request.user`; no tenant in state or session for QB.
- `QuickBooksToken.objects.update_or_create(realm_id=realm_id, defaults={...})` — keyed by `realm_id` only (and optional user), no tenant.

---

## 5. API Calls to QuickBooks

### 5.1 How the connection/token is chosen

**Fiscal app (QuickBooksConnection):**

- **File:** `fiscal/services/qb_client.py` (line 25)

```python
conn = conn or QuickBooksConnection.objects.filter(is_active=True).first()
```

- **File:** `fiscal/services/dashboard_service.py` (line 211)

```python
conn = QuickBooksConnection.objects.filter(is_active=True).first()
```

- **File:** `fiscal/views_fdms.py` (lines 671, 740)

```python
qb_connection = QuickBooksConnection.objects.filter(is_active=True).first()
...
conn = QuickBooksConnection.objects.filter(is_active=True).first()
```

**Finding:** Every use of `QuickBooksConnection` in the fiscal app uses **the first active connection in the database**. There is no `tenant=request.tenant` (or similar) filter. So all tenants effectively share one “first” connection.

**QuickBooks app (QuickBooksToken):**

- Token is resolved by `realm_id` (and optionally `user`) in `get_valid_token(realm_id, user=None)`.
- `realm_id` is passed from webhook payload, query params, or request body — not derived from `request.tenant`. So API calls are not tied to the current tenant.

### 5.2 Use of realm_id in API URL

**File:** `quickbooks/client.py` (line 70)

```python
return f"{self._base_url}/v3/company/{self.realm_id}/{path}"
```

- The client uses the `realm_id` associated with the token/connection it was given. The problem is how that connection/token is chosen (global or by realm_id with no tenant mapping), not the URL shape.

---

## 6. Token Refresh Logic

### 6.1 Fiscal app — `QuickBooksConnection`

**File:** `fiscal/services/qb_oauth.py` (lines 104–143)

- `refresh_tokens(conn)` takes a single `QuickBooksConnection` instance.
- It decrypts `conn.refresh_token_encrypted`, calls Intuit, then updates **that** `conn` only.
- **Tenant:** N/A — the `conn` passed in is whatever the caller chose; everywhere that calls this uses the global “first active” connection.

### 6.2 QuickBooks app — `QuickBooksToken`

**File:** `quickbooks/utils.py` — `refresh_quickbooks_token(token)` updates the given token row. Lookup is by `realm_id` (and optionally user), not tenant.

**Conclusion:** Refresh logic correctly updates only the specific token/connection row; the issue is that the row is not selected by tenant.

---

## 7. Global Storage of QuickBooks Tokens

**File:** `fdms_project/settings.py` (lines 231–238, 240–255)

```python
# QuickBooks Integration: use env only; no default client secrets in repo.
QB_CLIENT_ID = os.environ.get("QB_CLIENT_ID", "")
QB_CLIENT_SECRET = os.environ.get("QB_CLIENT_SECRET", "")
QB_REDIRECT_URI = os.environ.get("QB_REDIRECT_URI", "")
QB_WEBHOOK_VERIFIER = os.environ.get("QB_WEBHOOK_VERIFIER", "")
QB_REALM_ID = os.environ.get("QB_REALM_ID", "")
QB_ACCESS_TOKEN = os.environ.get("QB_ACCESS_TOKEN", "")
```

**Usage of global token/realm:**

- **File:** `fiscal/services/qb_service.py` (lines 41–44, 84–88)

```python
def get_qb_access_token() -> str:
    """Return QB access token from settings. Used for API calls (legacy path)."""
    return getattr(settings, "QB_ACCESS_TOKEN", "") or ""
...
token = get_qb_access_token()
if not token:
    logger.warning("QB_ACCESS_TOKEN not set; cannot fetch from QB API")
    return None
```

- **File:** `fiscal/services/fiscal_service.py` (lines 30–31)

```python
realm_id = getattr(settings, "QB_REALM_ID", "") or ""
...
payload = fetch_invoice_from_qb(receipt.qb_id, realm_id, entity_name)
```

**Finding:** **Global storage risk.** When no OAuth token exists for a realm, the code can fall back to a single `QB_ACCESS_TOKEN` and `QB_REALM_ID` from environment/settings. That is one global credential for the whole application, not per tenant.

---

## 8. Tenant Isolation Checks

### 8.1 QuickBooksConnection / QuickBooksInvoice

- **QuickBooksConnection:** Never filtered by `tenant`. Always `.filter(is_active=True).first()`.
- **QuickBooksInvoice:** No `tenant` (or `device`) FK. All invoices are in one global pool; listing is capped (e.g. 500/100) but not scoped by tenant.
- **Dashboard:** `get_quickbooks_stub(tenant=tenant)` receives `request.tenant` but does **not** filter connections or invoices by tenant; it still uses the first active connection and a global invoice list.

### 8.2 Fiscalisation and device choice

**File:** `fiscal/services/qb_fiscalisation.py` (line 147)

```python
device = FiscalDevice.objects.filter(is_registered=True).first()
```

**File:** `fiscal/services/qb_service.py` (line 169)

```python
device = FiscalDevice.objects.filter(is_registered=True).first()
```

**Finding:** QB-driven fiscalisation and receipt creation use **the first registered device in the system**, not `request.tenant` or the tenant that “owns” the QuickBooks connection. So one tenant’s QB data can be fiscalised on another tenant’s device.

### 8.3 Summary

- Credentials: not linked to tenant; one “first” connection or global env token.
- Invoices: global list; no tenant filter.
- Device for fiscalisation: global first device.
- Risk: Any tenant (or webhook) can effectively use the same QB connection and same device; no tenant isolation.

---

## 9. Report Summary Table

| Item | Status | Details |
|------|--------|---------|
| **Where credentials are stored** | Two stores | (1) `fiscal.QuickBooksConnection` (encrypted tokens), (2) `quickbooks.QuickBooksToken` (plain tokens). |
| **Linked to Tenant?** | No | Neither model has a `tenant` FK or any tenant field. |
| **OAuth callback tenant binding** | No | Callback uses only `realmId` from query; no `request.tenant`, session tenant_slug, or state. |
| **API calls use tenant context?** | No | Connection/token chosen by “first active” or `realm_id`/user; never `request.tenant`. |
| **Token refresh tenant-scoped?** | N/A | Refresh updates the given row only; row selection is not tenant-scoped. |
| **Global token storage** | Yes | `QB_REALM_ID` and `QB_ACCESS_TOKEN` in settings; used as fallback for API calls and realm. |
| **Cross-tenant risks** | Yes | Shared connection, global device for fiscalisation, global invoice list, possible use of one tenant’s QB data by another. |

---

## 10. Recommended Fixes

1. **Add tenant to credential model (fiscal)**  
   - Add `tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, unique=True)` (or OneToOne) to `QuickBooksConnection`.  
   - Migrate existing rows (e.g. assign to a single “default” tenant or leave null and backfill).  
   - Enforce one active connection per tenant (e.g. unique on `tenant` or `(tenant, is_active)` as appropriate).

2. **OAuth flow tenant-aware**  
   - On “Connect QuickBooks”, store current tenant in OAuth `state` (e.g. `tenant_slug` or signed payload).  
   - In callback, parse `state`, resolve tenant, then save tokens to `QuickBooksConnection` with `tenant=tenant` (create/update by tenant, not only by `realm_id`).

3. **All connection lookups by tenant**  
   - Replace every `QuickBooksConnection.objects.filter(is_active=True).first()` with a tenant-scoped lookup, e.g.  
     `QuickBooksConnection.objects.filter(tenant=request.tenant, is_active=True).first()`.  
   - Ensure `request.tenant` is set by middleware for all QB views (or explicitly resolve from session/state).

4. **QuickBooksInvoice and device by tenant**  
   - Add `tenant` FK to `QuickBooksInvoice` (and backfill from receipt/device if possible).  
   - Filter invoice lists and fiscalisation by `request.tenant` (or by tenant implied by the QB connection).  
   - In `qb_fiscalisation.py` and `qb_service.py`, resolve device as `FiscalDevice.objects.filter(tenant=request.tenant or connection.tenant, is_registered=True).first()` (or equivalent); do not use global `.first()`.

5. **Remove or restrict global token fallback**  
   - Prefer OAuth-only path; if legacy env token is kept, document that it is single-tenant only and deprecate.  
   - Do not use `QB_ACCESS_TOKEN` / `QB_REALM_ID` when a tenant context exists without mapping that realm to a tenant.

6. **quickbooks app (optional but recommended)**  
   - If the app remains, add `tenant` to `QuickBooksToken` and key lookups by `(tenant, realm_id)` or equivalent so tokens are per-tenant.  
   - Ensure any code that passes `realm_id` to this app (e.g. webhooks) resolves tenant from realm_id (e.g. via a Tenant ↔ realm_id mapping) and uses only that tenant’s tokens.

7. **Tests**  
   - Add tests that: (1) create two tenants with two different QB connections, (2) call QB APIs and fiscalisation as each tenant, (3) assert each tenant only sees and uses its own connection and data.

---

## 11. File Paths Reference

| Topic | File path |
|-------|-----------|
| QuickBooksConnection model | `fiscal/models.py` |
| QuickBooksToken model | `quickbooks/models.py` |
| OAuth exchange (fiscal) | `fiscal/services/qb_oauth.py` |
| OAuth callback (fiscal) | `fiscal/views_api.py` (`api_qb_oauth_callback`) |
| Connection lookup (no tenant) | `fiscal/services/qb_client.py`, `fiscal/services/dashboard_service.py`, `fiscal/views_fdms.py` |
| Token refresh (fiscal) | `fiscal/services/qb_oauth.py` (`refresh_tokens`) |
| Global token/realm | `fdms_project/settings.py`, `fiscal/services/qb_service.py`, `fiscal/services/fiscal_service.py` |
| Device selection (global) | `fiscal/services/qb_fiscalisation.py`, `fiscal/services/qb_service.py` |
| Dashboard QB stub | `fiscal/services/dashboard_service.py` (`get_quickbooks_stub`) |

---

*End of audit report.*
