# QuickBooks SaaS Architecture Audit

**Date:** 2026-03-10  
**Scope:** Django FDMS multi-tenant platform — QuickBooks integration  
**Goal:** Confirm architecture is **one developer app → tenant-level connections → tenant-specific API calls**.

---

## Classification

**CORRECT SaaS DESIGN**

The QuickBooks integration uses a single Intuit developer application (QB_CLIENT_ID / QB_CLIENT_SECRET) for the entire system. Each tenant connects its own QuickBooks company via OAuth; tokens are stored per tenant in `QuickBooksConnection`. API calls and webhooks resolve the connection by tenant or by `realm_id` and use that connection’s tokens only. There are no per-tenant developer apps and no use of global QB_ACCESS_TOKEN / QB_REALM_ID in the fiscal codebase.

---

## 1. System OAuth credentials

### 1.1 Settings and .env

**File:** `fdms_project/settings.py`

- **.env loading (lines 19–26):** A `.env` file in the project root is loaded at startup; each `KEY=VALUE` line is applied with `os.environ.setdefault(key.strip(), value.strip())`. Variables are not tenant-scoped.
- **QB variables (lines 232–234):**
  - `QB_CLIENT_ID = os.environ.get("QB_CLIENT_ID", "")`
  - `QB_CLIENT_SECRET = os.environ.get("QB_CLIENT_SECRET", "")`
  - `QB_REDIRECT_URI = os.environ.get("QB_REDIRECT_URI", "")`

**Result:** All three exist, are defined once, and are global (environment / settings). No tenant-specific overrides.

### 1.2 Usage of credentials

**File:** `fiscal/services/qb_oauth.py`

- `get_qb_credentials()` (lines 21–24) returns `(getattr(settings, "QB_CLIENT_ID", "") or "", getattr(settings, "QB_CLIENT_SECRET", "") or "")`. It takes **no** `tenant` (or any) parameter.
- `get_authorize_url(state=..., request=...)` and `exchange_code_for_tokens(..., tenant=tenant)` both call `get_qb_credentials()` with no tenant.
- `refresh_tokens(conn)` also uses `get_qb_credentials()`; the connection is tenant-scoped, but the client_id/client_secret are not.

**File:** `fiscal/services/qb_client.py`

- `get_quickbooks_client(conn=None, tenant=None)` calls `get_qb_credentials()` only to build the QuickBooks client; the **tokens** and **company_id** come from `conn` (tenant’s connection).

**Search:** No code in the project switches `client_id` or `client_secret` by tenant. No `tenant.client_id`, no `QuickBooksApp` model, no `client_id` stored in the database for tenants.

**Result:** OAuth credentials are global; architecture is one developer app for the system.

---

## 2. QuickBooksConnection model

**File:** `fiscal/models.py` (lines 669–701)

```python
class QuickBooksConnection(models.Model):
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="quickbooks_connection",
    )
    realm_id = models.CharField(max_length=50, db_index=True)
    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

- **tenant:** OneToOne to `tenants.Tenant`, required (no `null=True`/`blank=True`). Connection is tied to a single tenant.
- **realm_id:** Stored; identifies the QuickBooks company.
- **access_token_encrypted / refresh_token_encrypted:** Stored per connection (encrypted with ENC: prefix enforced in `save()`).
- **token_expires_at:** Stored.

**Result:** Model matches the expected SaaS structure: tenant-linked, tokens and realm_id per tenant.

---

## 3. OAuth authorization flow

**File:** `fiscal/views_api.py` — `api_qb_oauth_connect` (lines 353–364)

- Requires `request.tenant`; otherwise redirects to `select_tenant`.
- `state = tenant.slug`.
- Calls `get_authorize_url(state=state, request=request)`.

**File:** `fiscal/services/qb_oauth.py` — `get_authorize_url` (lines 36–50)

- Base URL: `INTUIT_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"`.
- Parameters: `client_id`, `response_type`: `"code"`, `scope`: `"com.intuit.quickbooks.accounting"`, `redirect_uri`, `state`: passed-in (tenant slug).

**Result:** Redirect URL and parameters are correct; `state` carries the tenant identifier (tenant slug).

---

## 4. OAuth callback logic

**File:** `fiscal/views_api.py` — `api_qb_oauth_callback` (lines 367–390)

- `tenant_slug = request.GET.get("state")`.
- `tenant = Tenant.objects.get(slug=tenant_slug, is_active=True)` (with 400 on missing/invalid).
- Tenant mismatch check: `if tenant.slug != request.GET.get("state"): return JsonResponse({"error": "Tenant mismatch."}, status=400)`.
- `exchange_code_for_tokens(code, redirect_uri, realm_id, tenant=tenant)`.

**File:** `fiscal/services/qb_oauth.py` — `exchange_code_for_tokens` (lines 97–106)

- Tokens saved with:  
  `QuickBooksConnection.objects.update_or_create(tenant=tenant, defaults={"realm_id": realm_id, "access_token_encrypted": ..., "refresh_token_encrypted": ..., "token_expires_at": ..., "is_active": True})`.
- Tenant is required; no path saves tokens without tenant context.

**Result:** Callback resolves tenant from `state` and persists tokens only via `update_or_create(tenant=tenant, ...)`.

---

## 5. Token usage in API calls

**Pattern:** Connection is always resolved by tenant or by `realm_id`; then that connection’s `realm_id` and decrypted access token are used.

- **fiscal/services/qb_client.py** — `get_quickbooks_client(conn=None, tenant=None)`:
  - If only `tenant` given: `conn = QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()`.
  - Uses `decrypt_string(conn.access_token_encrypted)`, `conn.realm_id` as `company_id`; client_id/client_secret from `get_qb_credentials()` (global).
- **fiscal/services/qb_service.py** — `fetch_invoice_from_qb(invoice_id, realm_id, ...)`:
  - `conn = QuickBooksConnection.objects.filter(realm_id=realm_id, is_active=True).first()`.
  - `token = decrypt_string(conn.access_token_encrypted)`; `Authorization: Bearer {token}`; URL uses `realm_id`.
- **fiscal/services/fiscal_service.py:** Gets `tenant` from receipt’s device, then `conn = QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()`, then `realm_id = conn.realm_id`.
- **fiscal/services/qb_sync.py:** Resolves `conn` by `tenant` (or uses passed `conn`).
- **fiscal/services/dashboard_service.py:** `QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()`.
- **fiscal/views_fdms.py:** Same tenant-scoped lookup for settings/invoices.

**Search:** No use of `QB_ACCESS_TOKEN` or `QB_REALM_ID` from settings in fiscal code. Comment in `qb_service.py` states: “Tenant-scoped: uses QuickBooksConnection for realm_id (no global QB_ACCESS_TOKEN).” The only `HTTP_X_QB_REALM_ID` reference is a request header for logging, not settings.

**Result:** API usage is tenant-scoped via `QuickBooksConnection`; no global token/realm fallback.

---

## 6. Webhook handling

**File:** `fiscal/services/qb_service.py` — `handle_qb_event(entity_name, entity_id, realm_id)` (lines 132–158)

- `conn = QuickBooksConnection.objects.filter(realm_id=realm_id, is_active=True).select_related("tenant").first()`.
- If no conn or no `conn.tenant_id`: log and return.
- `tenant = conn.tenant`.
- Subsequent logic (e.g. receipt creation, fiscalisation) uses this `tenant`.

**File:** `fiscal/views_api.py` — webhook views

- Resolve `realm_id` from payload; then `conn = QuickBooksConnection.objects.filter(realm_id=realm_id, is_active=True).select_related("tenant").first()` and use `conn.tenant` where tenant is needed.

**File:** `quickbooks/tasks.py` — `process_qb_invoice_webhook`

- Resolves tenant via `QuickBooksConnection.objects.filter(realm_id=realm_id, is_active=True).select_related("tenant").first()` and uses it for idempotency and fiscalisation.

**Result:** Webhooks resolve tenant as **realm_id → QuickBooksConnection → tenant**. No global realm or token.

---

## 7. Refresh token logic

**File:** `fiscal/services/qb_oauth.py` — `refresh_tokens(conn: QuickBooksConnection)` (lines 114–156)

- Decrypts `conn.refresh_token_encrypted` via `decrypt_string(conn.refresh_token_encrypted)`.
- POST to Intuit token URL with `grant_type=refresh_token` and that refresh token.
- Updates only that connection:  
  `conn.access_token_encrypted = encrypt_string(access)`;  
  `conn.refresh_token_encrypted = encrypt_string(refresh)`;  
  `conn.token_expires_at = ...`;  
  `conn.save(update_fields=[...])`.
- Client_id/client_secret for the POST come from `get_qb_credentials()` (global); the refreshed tokens are written only to the passed `conn`.

**Result:** Refresh uses the connection’s refresh token and updates only that connection; no global token update.

---

## 8. Multiple developer apps

**Searches:**

- `tenant.client_id` / `client_id` stored in DB / `QuickBooksApp` model: **no matches** in the project.
- Credentials are read only from settings (`QB_CLIENT_ID`, `QB_CLIENT_SECRET`); no model or tenant field holds a per-tenant client_id or client_secret.

**Note:** The `quickbooks` app (separate from `fiscal`) uses `QUICKBOOKS_CLIENT_ID` and `QUICKBOOKS_CLIENT_SECRET` in `quickbooks/services.py` and `quickbooks/utils.py`. That is a second, optional integration path (e.g. different URLs or legacy). The **FDMS QuickBooks flow** used by the multi-tenant FDMS UI and webhooks is the one in `fiscal` using `QB_*` and `QuickBooksConnection`; that flow uses a single developer app.

**Result:** No per-tenant developer apps; one app for the system in the fiscal QuickBooks integration.

---

## 9. Architecture summary

| Criterion | Status | Evidence |
|-----------|--------|----------|
| OAuth credentials global | Yes | QB_CLIENT_ID, QB_CLIENT_SECRET, QB_REDIRECT_URI in settings from env; get_qb_credentials() has no tenant parameter; no tenant-scoped client_id/secret. |
| QuickBooksConnection tenant-scoped | Yes | OneToOne to Tenant; realm_id and encrypted tokens per row; update_or_create(tenant=tenant, ...) on callback. |
| API calls use tenant tokens | Yes | Conn resolved by tenant or realm_id; Authorization and realm from conn; no QB_ACCESS_TOKEN/QB_REALM_ID. |
| Webhooks use realm_id → connection → tenant | Yes | handle_qb_event, views_api webhooks, and quickbooks/tasks resolve conn by realm_id and use conn.tenant. |
| Refresh updates only one connection | Yes | refresh_tokens(conn) updates only the given conn’s token fields. |
| Multiple developer apps | No | No tenant.client_id, no DB-stored client_id, no QuickBooksApp; single QB_* app for fiscal flow. |

**Conclusion:** The QuickBooks integration follows the intended **SaaS OAuth architecture**: one system-level developer application, tenant-level QuickBooks connections (one per tenant), and tenant-specific API calls and webhooks using those connections only. Classified as **CORRECT SaaS DESIGN**.

---

*End of QuickBooks SaaS architecture audit.*
