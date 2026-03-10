# QuickBooks OAuth Token Lifecycle Audit

**Date:** 2026-03-09  
**Scope:** QuickBooks Online OAuth 2.0 integration in Django FDMS multi-tenant application  
**Goal:** Verify how access tokens are obtained, stored, refreshed, and used, with tenant isolation.

---

## Executive Summary

| Area | Status | Notes |
|------|--------|--------|
| OAuth authorization flow | ✅ Compliant | Correct Intuit URL; `state` = tenant slug |
| OAuth callback | ✅ Compliant | Receives code, realmId, state; tenant from state |
| Code exchange for tokens | ✅ Compliant | POST to bearer endpoint; Basic auth; grant_type and redirect_uri correct |
| Token storage | ✅ Compliant | Tenant-linked model; encrypted at rest |
| Token refresh | ✅ Compliant | POST with refresh_token; updates only that connection |
| API usage | ✅ Compliant | Token loaded via tenant or realm_id → connection |
| Global credential fallback | ✅ Removed | No code uses `QB_ACCESS_TOKEN` / `QB_REALM_ID` for API calls |
| Tenant isolation | ✅ Enforced | Connection and usage are per-tenant |

**Security risks:** Low. Remaining items: (1) `QB_ACCESS_TOKEN` / `QB_REALM_ID` still in settings (dead config); (2) ensure `FDMS_ENCRYPTION_KEY` is set in production so tokens are encrypted.

---

## 1. OAuth Authorization Flow

### 1.1 Location

- **File:** `fiscal/views_api.py`  
- **Function:** `api_qb_oauth_connect` (lines 353–364)  
- **URL name:** `api_qb_oauth_connect`  
- **Route:** `/api/integrations/quickbooks/oauth/connect/`

### 1.2 Redirect URL

- **Configured in code:** `fiscal/services/qb_oauth.py`  
- **Constant:** `INTUIT_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"` (line 16)  
- **Settings:** `fdms_project/settings.py` line 253: `QUICKBOOKS_OAUTH_AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"` (quickbooks app; fiscal uses its own constant)

**Verification:** ✅ Redirect uses `https://appcenter.intuit.com/connect/oauth2`.

### 1.3 Parameters

Built in `fiscal/services/qb_oauth.py`, `get_authorize_url()` (lines 36–50):

```python
params = {
    "client_id": client_id,           # from get_qb_credentials() → QB_CLIENT_ID
    "response_type": "code",
    "scope": "com.intuit.quickbooks.accounting",
    "redirect_uri": redirect_uri,     # QB_REDIRECT_URI or request.build_absolute_uri("/api/integrations/quickbooks/oauth/callback/")
    "state": state or "qb_connect",   # passed in
}
qs = "&".join(f"{k}={v}" for k, v in params.items())
return f"{INTUIT_AUTH_URL}?{qs}"
```

**Verification:** ✅ All required parameters present: `client_id`, `redirect_uri`, `response_type=code`, `scope=com.intuit.quickbooks.accounting`, `state`.

### 1.4 State parameter (tenant identifier)

In `fiscal/views_api.py` (lines 356–361):

```python
tenant = getattr(request, "tenant", None)
if not tenant:
    return redirect("select_tenant")
state = tenant.slug
url = get_authorize_url(state=state, request=request)
```

**Verification:** ✅ `state` is the current tenant’s slug. No tenant → user is sent to tenant selection; no global connect.

---

## 2. OAuth Callback

### 2.1 Location

- **File:** `fiscal/views_api.py`  
- **Function:** `api_qb_oauth_callback` (lines 367–389)  
- **Route:** `/api/integrations/quickbooks/oauth/callback/`

### 2.2 Query parameters

```python
code = request.GET.get("code")
realm_id = request.GET.get("realmId")
tenant_slug = request.GET.get("state")
if not code or not realm_id:
    return redirect("fdms_qb_invoices")
if not tenant_slug:
    return JsonResponse({"error": "Missing state (tenant)."}, status=400)
```

**Verification:** ✅ Callback uses `code`, `realmId`, and `state`. Missing `code` or `realm_id` → redirect to QB invoices; missing `state` → 400 with “Missing state (tenant).”.

### 2.3 Tenant resolution

```python
try:
    tenant = Tenant.objects.get(slug=tenant_slug, is_active=True)
except Tenant.DoesNotExist:
    return JsonResponse({"error": "Invalid tenant."}, status=400)
redirect_uri = get_redirect_uri(request)
data, err = exchange_code_for_tokens(code, redirect_uri, realm_id, tenant=tenant)
```

**Verification:** ✅ Tenant is resolved from `state` (tenant slug). Invalid slug → 400. Tokens are passed to `exchange_code_for_tokens(..., tenant=tenant)`.

---

## 3. Code Exchange for Tokens

### 3.1 Location

- **File:** `fiscal/services/qb_oauth.py`  
- **Function:** `exchange_code_for_tokens(code, redirect_uri, realm_id, tenant=None)` (lines 54–107)

### 3.2 Request

```python
INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

resp = requests.post(
    INTUIT_TOKEN_URL,
    auth=(client_id, client_secret),   # HTTP Basic: client_id:client_secret
    headers={"Accept": "application/json"},
    data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    },
    timeout=30,
)
```

**Verification:**  
✅ POST to `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`  
✅ Authorization: HTTP Basic with `client_id` and `client_secret` from `get_qb_credentials()` (settings `QB_CLIENT_ID`, `QB_CLIENT_SECRET`)  
✅ `grant_type=authorization_code`, `code`, `redirect_uri` sent  
✅ Caller ensures `tenant` is set; otherwise function returns error “Tenant required for QuickBooks connection”.

### 3.3 Response parsing

```python
data = resp.json()
access = data.get("access_token")
refresh = data.get("refresh_token")
expires_in = int(data.get("expires_in", 3600))
if not access or not refresh:
    return None, "Missing access_token or refresh_token"
# ...
expires_at = timezone.now() + timedelta(seconds=expires_in)
```

**Verification:** ✅ Extracts `access_token`, `refresh_token`, `expires_in` (default 3600). Fails if either token is missing.

---

## 4. Token Storage

### 4.1 Model

- **File:** `fiscal/models.py`  
- **Model:** `QuickBooksConnection` (lines 669–694)

```python
class QuickBooksConnection(models.Model):
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="quickbooks_connection",
        null=True,
        blank=True,
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

**Verification:**  
✅ Tenant link: `OneToOneField` to `tenants.Tenant`  
✅ `realm_id`, `access_token_encrypted`, `refresh_token_encrypted`, `token_expires_at`  
✅ Tokens stored in encrypted fields (see below).

**Note:** `tenant` is nullable for legacy/migrations; OAuth flow always passes tenant, so new connections are tenant-bound.

### 4.2 Persistence after code exchange

In `qb_oauth.py` (lines 97–105):

```python
conn, _ = QuickBooksConnection.objects.update_or_create(
    tenant=tenant,
    defaults={
        "realm_id": realm_id,
        "access_token_encrypted": encrypt_string(access),
        "refresh_token_encrypted": encrypt_string(refresh),
        "token_expires_at": expires_at,
        "is_active": True,
    },
)
```

**Verification:** ✅ One connection per tenant (`update_or_create(tenant=tenant, ...)`). Tokens stored only in encrypted form.

### 4.3 Encryption

- **File:** `fiscal/services/key_storage.py`  
- **Functions:** `encrypt_string(plain)` (line 65), `decrypt_string(stored)` (line 75)  
- **Mechanism:** Fernet (symmetric) using `FDMS_ENCRYPTION_KEY` (env). Prefix `ENC:` + base64 ciphertext.  
- **Usage:** All reads/writes of `access_token_encrypted` and `refresh_token_encrypted` go through `encrypt_string` / `decrypt_string`.

**Verification:** ✅ Tokens are encrypted before storage. If `FDMS_ENCRYPTION_KEY` is not set, `encrypt_string` returns plaintext (fallback); production should set the key.

---

## 5. Token Refresh

### 5.1 Location

- **File:** `fiscal/services/qb_oauth.py`  
- **Function:** `refresh_tokens(conn: QuickBooksConnection)` (lines 111–150)

### 5.2 Request

```python
resp = requests.post(
    INTUIT_TOKEN_URL,   # https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer
    auth=(client_id, client_secret),
    headers={"Accept": "application/json"},
    data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,   # decrypted from conn.refresh_token_encrypted
    },
    timeout=30,
)
```

**Verification:** ✅ POST to same bearer URL; Basic auth; `grant_type=refresh_token`; `refresh_token` from the given connection.

### 5.3 Updating only that tenant’s record

```python
# refresh_token from conn
refresh_token = decrypt_string(conn.refresh_token_encrypted)
# ... POST ...
access = data.get("access_token")
refresh = data.get("refresh_token") or refresh_token
# ...
conn.access_token_encrypted = encrypt_string(access)
conn.refresh_token_encrypted = encrypt_string(refresh)
conn.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
conn.save(update_fields=["access_token_encrypted", "refresh_token_encrypted", "token_expires_at", "updated_at"])
```

**Verification:** ✅ Only the passed `QuickBooksConnection` instance is updated. Callers resolve `conn` by tenant or by `realm_id` (which is 1:1 with a tenant after OAuth). No cross-tenant update.

---

## 6. API Usage (Access Token Loading)

### 6.1 Tenant-scoped client (sync / UI)

- **File:** `fiscal/services/qb_client.py`  
- **Function:** `get_quickbooks_client(conn=None, tenant=None)`

```python
if conn is None and tenant is not None:
    conn = QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()
if not conn or not conn.access_token_encrypted:
    return None
# Optional refresh if expired
if conn.token_expires_at and conn.token_expires_at <= timezone.now():
    ok, err = refresh_tokens(conn)
    # ...
access = decrypt_string(conn.access_token_encrypted)
# ...
return QuickBooks(..., access_token=access, ..., company_id=conn.realm_id)
```

**Verification:** ✅ When called with `tenant` (e.g. `request.tenant`), connection is loaded with `QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()`. Token is decrypted and used in the client. No global lookup.

### 6.2 Fetch invoice by realm_id (webhook / tasks)

- **File:** `fiscal/services/qb_service.py`  
- **Function:** `fetch_invoice_from_qb(invoice_id, realm_id, entity_name)`

```python
conn = QuickBooksConnection.objects.filter(realm_id=realm_id, is_active=True).first()
# ...
token = decrypt_string(conn.access_token_encrypted)
# ...
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
resp = requests.get(url, headers=headers, ...)
```

**Verification:** ✅ Token is taken from the connection for the given `realm_id`. `realm_id` comes from webhook payload or from a tenant’s stored connection; tenant is resolved from the same connection when needed (e.g. `handle_qb_event`). Authorization header uses that tenant’s token only.

### 6.3 Other call sites

- **qb_sync.sync_from_quickbooks:** Resolves `conn` from `tenant` (or uses passed `conn`); uses `get_quickbooks_client` or equivalent with that connection.  
- **fiscal_service.fiscalise_receipt:** Gets `tenant` from `receipt.device.tenant`, then `QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()`.  
- **views_api (sync, retry, invoices, fiscalise):** Use `request.tenant` and filter connection or invoices by tenant.  
- **dashboard_service.get_quickbooks_stub:** Uses `QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()` when `tenant` is provided.

**Verification:** ✅ No API call uses a connection without tenant or realm_id context. No `QuickBooksConnection.objects.get(tenant=request.tenant)` without also ensuring the view is tenant-scoped (middleware sets `request.tenant`).

---

## 7. Global Credential Fallback

### 7.1 Settings

- **File:** `fdms_project/settings.py` (lines 237–238):

```python
QB_REALM_ID = os.environ.get("QB_REALM_ID", "")
QB_ACCESS_TOKEN = os.environ.get("QB_ACCESS_TOKEN", "")
```

These are still defined and documented in `ENV.md` as legacy/optional.

### 7.2 Code usage

- **Searched:** All `fiscal` Python code for `QB_ACCESS_TOKEN`, `QB_REALM_ID`, and any `get_qb_access_token`-style helper.  
- **Result:** No fiscal code path uses `QB_ACCESS_TOKEN` or `QB_REALM_ID` for QuickBooks API calls.  
- **Comment in qb_service:** “Tenant-scoped: uses QuickBooksConnection for realm_id (no global QB_ACCESS_TOKEN).”

**Verification:** ✅ No global credential fallback in application code. Settings/ENV entries are legacy; consider removing or clearly marking as unused to avoid future misuse.

---

## 8. Tenant Isolation Summary

| Step | Tenant binding |
|------|----------------|
| Connect | User must have `request.tenant`; `state=tenant.slug` |
| Callback | Tenant from `state`; tokens stored with `tenant=tenant` |
| Storage | `QuickBooksConnection` has `OneToOneField( Tenant )`; `update_or_create(tenant=tenant, ...)` |
| Refresh | Operates on single `conn`; `conn` is always tenant- or realm-scoped |
| Sync / UI | `conn = QuickBooksConnection.objects.filter(tenant=tenant, ...).first()` |
| Webhook / fetch | `realm_id` → `QuickBooksConnection` → same connection’s token; tenant resolved from connection when needed |
| Global fallback | None; no use of `QB_ACCESS_TOKEN` / `QB_REALM_ID` in code |

Tenant isolation is enforced across the OAuth and API lifecycle.

---

## 9. Security Risks and Recommendations

| Risk | Level | Recommendation |
|------|--------|----------------|
| `QB_ACCESS_TOKEN` / `QB_REALM_ID` in settings | Low | Remove from settings or document as unused; avoid using as fallback. |
| Encryption key not set | Medium | Set `FDMS_ENCRYPTION_KEY` in production so tokens are not stored in plaintext. |
| `QuickBooksConnection.tenant` nullable | Low | After backfill, consider making `tenant` non-null and dropping null paths. |
| State tampering | Low | Callback validates tenant by slug and `is_active`; consider adding a signed or HMAC state if needed for higher assurance. |

---

## 10. File Reference

| Purpose | File path |
|--------|-----------|
| OAuth connect view | `fiscal/views_api.py` – `api_qb_oauth_connect` |
| OAuth callback view | `fiscal/views_api.py` – `api_qb_oauth_callback` |
| Authorize URL, code exchange, refresh | `fiscal/services/qb_oauth.py` |
| Token storage model | `fiscal/models.py` – `QuickBooksConnection` |
| Encryption | `fiscal/services/key_storage.py` – `encrypt_string`, `decrypt_string` |
| QB client (tenant-scoped) | `fiscal/services/qb_client.py` – `get_quickbooks_client` |
| Fetch invoice (realm_id → token) | `fiscal/services/qb_service.py` – `fetch_invoice_from_qb`, `refresh_tokens` usage |
| URL routes | `fiscal/urls.py` – `api_qb_oauth_connect`, `api_qb_oauth_callback` |
| Settings (QB env) | `fdms_project/settings.py` – QB_*, QUICKBOOKS_* |

---

*End of QuickBooks OAuth token lifecycle audit.*
