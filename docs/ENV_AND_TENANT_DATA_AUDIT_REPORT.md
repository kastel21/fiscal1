# Environment Variables & Tenant Data Audit Report

**Project:** FiscalFlow (Django FDMS)  
**Scope:** Verify environment variables are used only for system-level configuration; tenant-specific data must be stored in the database.  
**Result:** **SAFE CONFIGURATION**

---

## 1. Environment variable loading

- **Location:** `fdms_project/settings.py` (lines 19–27).
- **Mechanism:** Custom loader (no `python-dotenv`). Reads `BASE_DIR / ".env"` and for each non-empty, non-comment line containing `=`, sets `os.environ.setdefault(key.strip(), value.strip())`.
- **Scope:** All runtime env reads use `os.environ.get(...)` (or equivalent) in `settings.py`, `key_storage.py`, middleware, and a few management commands. No other dotenv/load_dotenv usage.

---

## 2. Contents of `.env`

**Current `.env` (project root):**

| Variable             | Purpose                          | Classification     |
|----------------------|----------------------------------|--------------------|
| `DATABASE_URL`       | PostgreSQL connection            | System             |
| `QB_CLIENT_ID`       | QuickBooks OAuth app (global)    | System             |
| `QB_CLIENT_SECRET`   | QuickBooks OAuth app (global)     | System             |
| `QB_REDIRECT_URI`    | QuickBooks OAuth redirect        | System             |
| `FDMS_ENCRYPTION_KEY`| Fernet key for token/key encryption | System         |

**Detected:** No tenant-specific variables in `.env`.

**Sensitive-tenant patterns searched (not present in `.env`):**  
`access_token`, `refresh_token`, `realm_id`, `device_certificate`, `fiscal_device`, `tenant_id`, `certificate`, `private_key`.

---

## 3. Environment variables used in the project

**System-level only (from `settings.py` and other modules):**

- **Django:** `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_STATIC_ROOT`, `DJANGO_MEDIA_ROOT`, `DJANGO_MEDIA_URL`, `DJANGO_SECURE_SSL_REDIRECT`
- **Database:** `DATABASE_URL`
- **Celery/Redis:** `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ALWAYS_EAGER`, `REDIS_URL`
- **FDMS API (ZIMRA):** `FDMS_ENV`, `FDMS_BASE_URL`, `FDMS_DEVICE_ID`, `FDMS_DEVICE_SERIAL_NO`, `FDMS_ACTIVATION_KEY`, `FDMS_DEVICE_MODEL_NAME`, `FDMS_DEVICE_MODEL_VERSION`, `FDMS_PERSIST_PDF`, `ZIMRA_QR_URL`
- **Encryption:** `FDMS_ENCRYPTION_KEY` (used in `fiscal/services/key_storage.py`)
- **QuickBooks (app-level OAuth):** `QB_CLIENT_ID`, `QB_CLIENT_SECRET`, `QB_REDIRECT_URI`, `QB_WEBHOOK_VERIFIER`; also `QUICKBOOKS_*` in settings
- **Tenant/security:** `TENANT_KEYS_BASE_PATH`, `TENANT_HEADER_FOR_INTERNAL_API`, `INTERNAL_API_TOKEN`
- **Deployment:** `GUNICORN_ACCESS_LOG`, `GUNICORN_ERROR_LOG`, `BACKUP_DIR`, `PG_DUMP_PATH`, `SYNC_TARGET_DATABASE_URL`, etc.

**Note on `FDMS_DEVICE_*`:** These exist in `settings.py` / `settings_production.py` for optional single-tenant or registration use. The **fiscal application code does not use them** for resolving the active device at runtime. Device resolution is always via `FiscalDevice.objects.filter(tenant=..., is_registered=True)` (or similar). No tenant device data is read from the environment.

---

## 4. Tenant data in `.env` (critical check)

**Result:** **None.**

- No `access_token`, `refresh_token`, `realm_id`, `device_certificate`, `fiscal_device`, `tenant_id`, or similar tenant-specific secrets found in `.env`.

---

## 5. QuickBooksConnection model and token storage

**Location:** `fiscal/models.py` (QuickBooksConnection, ~lines 668–700).

**Fields verified:**

- `tenant` — `OneToOneField("tenants.Tenant")` ✅
- `realm_id` — `CharField` ✅
- `access_token_encrypted` — `TextField` ✅
- `refresh_token_encrypted` — `TextField` ✅
- `token_expires_at` — `DateTimeField` ✅

**Validation on save:**

- `save()` raises `ValueError` if `access_token_encrypted` or `refresh_token_encrypted` is set and does not start with `"ENC:"` (i.e. tokens must be stored encrypted).

**Conclusion:** QuickBooks tokens are stored only in the database, per tenant, and must be encrypted before save.

---

## 6. FiscalDevice model and device storage

**Location:** `fiscal/models.py` (FiscalDevice, ~lines 40–88).

**Fields verified:**

- `tenant` — `ForeignKey("tenants.Tenant")` ✅
- `device_id` — `IntegerField` ✅
- `certificate_pem` — `TextField` ✅
- `private_key_pem` — `TextField` ✅  
  (Decryption via `get_private_key_pem_decrypted()` using `decrypt_private_key()` from `key_storage`.)

**Conclusion:** Device identity and certificates are stored in the database per tenant. No device secrets are read from `.env` or environment at runtime for tenant resolution.

---

## 7. Token encryption usage

**Location:** `fiscal/services/key_storage.py`.

- **Fernet:** Used for encryption/decryption; key from `os.environ.get("FDMS_ENCRYPTION_KEY")`.
- **Functions:**  
  - `encrypt_string(plain)` — used for OAuth tokens; raises if `FDMS_ENCRYPTION_KEY` is not set.  
  - `decrypt_string(stored)` — used when reading tokens.  
  - `encrypt_private_key` / `decrypt_private_key` — for device private keys.

**QuickBooks token flow:**

- **Storage:** `fiscal/services/qb_oauth.py` — `encrypt_string(access)` / `encrypt_string(refresh)` before writing to `QuickBooksConnection` (e.g. lines 101–102, 149–150).
- **Retrieval:** `qb_service.py` and `qb_client.py` use `decrypt_string(conn.access_token_encrypted)` (and refresh) after loading the connection from the DB.

**Conclusion:** QuickBooks tokens are encrypted before storage and decrypted only when needed for API calls; encryption is required when storing tokens.

---

## 8. Global credential misuse (QB_ACCESS_TOKEN / QB_REFRESH_TOKEN / QB_REALM_ID)

**Search:** Project-wide for `QB_ACCESS_TOKEN`, `QB_REFRESH_TOKEN`, `QB_REALM_ID`.

**Result:**

- **`fdms_project/settings.py`:** No assignments to `QB_ACCESS_TOKEN`, `QB_REFRESH_TOKEN`, or `QB_REALM_ID`. ✅
- **`fiscal` app code:** No use of these names for API calls or token storage. ✅
- **Comments:** `fiscal/services/qb_service.py` states: “Tenant-scoped: uses QuickBooksConnection for realm_id (no global QB_ACCESS_TOKEN).”
- **References found only in:** Documentation and audit docs (e.g. `QUICKBOOKS_OAUTH_TOKEN_LIFECYCLE_AUDIT.md`, `QUICKBOOKS_TENANT_AUDIT_REPORT.md`) describing removal/avoidance; and `views_api.py` uses `HTTP_X_QB_REALM_ID` as a request header for logging, not as a stored credential.

**Conclusion:** No global QB token/realm environment variables are used; API calls use `QuickBooksConnection` resolved by tenant or `realm_id`.

---

## 9. Architecture compliance

**Intended split:**

- **System configuration (e.g. `.env`):** Secret key, DEBUG, DB URL, FDMS API base URL, FDMS env, encryption key, QB OAuth app credentials, Celery/Redis, etc.
- **Tenant data (database):** Tenant, QuickBooksConnection (realm_id, encrypted tokens), FiscalDevice (device_id, certificate, private key), Receipts, Company, etc.

**Verified:**

- `.env` and env-based settings contain only system-level configuration.
- QuickBooks tokens: stored in `QuickBooksConnection` (DB), encrypted with `FDMS_ENCRYPTION_KEY`.
- Device data: stored in `FiscalDevice` (DB); private keys decrypt via `FDMS_ENCRYPTION_KEY` (key in env, data in DB).
- Connection resolution: `QuickBooksConnection.objects.filter(tenant=request.tenant, ...)` or `filter(realm_id=realm_id, ...)`; no fallback to global env credentials.

**Model hierarchy (simplified):**

```
Tenant
   ├── QuickBooksConnection (realm_id, access_token_encrypted, refresh_token_encrypted)
   ├── FiscalDevice (device_id, certificate_pem, private_key_pem)
   ├── Receipts
   ├── Company
   └── ...
```

---

## 10. Summary table

| Check                               | Status |
|-------------------------------------|--------|
| Env vars loaded only from .env/settings | ✅ |
| `.env` contains only system vars   | ✅ |
| No tenant secrets in `.env`         | ✅ |
| QuickBooks tokens in DB (encrypted) | ✅ |
| FiscalDevice in DB (certs/keys)      | ✅ |
| encrypt_string / Fernet for tokens  | ✅ |
| No QB_ACCESS_TOKEN / QB_REALM_ID in code | ✅ |
| Architecture: system=env, tenant=DB | ✅ |

---

## Classification

**SAFE CONFIGURATION**

- Environment variables are used only for system-level configuration.
- Tenant-specific data (QuickBooks tokens, realm IDs, device certificates, fiscal data) is stored in the database.
- QuickBooks tokens are encrypted before storage and required to be encrypted on save.
- No global QB token/realm environment variables are present or used in the application code.

---

*Report generated from codebase audit. Re-run after any change to env loading, settings, or tenant-sensitive models.*
