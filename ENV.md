# Environment Variables

Set these in your environment or in a `.env` file in the project root (loaded automatically by `settings.py`). Values are not committed; use strong secrets in production.

---

## Django core

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | **Production** | Secret key for signing (never commit). | Long random string |
| `DJANGO_DEBUG` | No | `true` / `false`. Default: `true` (dev). Use `false` in production. | `false` |
| `DJANGO_ALLOWED_HOSTS` | No | Comma-separated hosts. | `takatel.tech,www.takatel.tech` |
| `DJANGO_STATIC_ROOT` | No | Where `collectstatic` writes files. | `/var/www/staticfiles` |
| `DJANGO_MEDIA_ROOT` | No | Media upload directory. | `/var/www/media` |
| `DJANGO_MEDIA_URL` | No | URL prefix for media. | `/media/` |
| `DJANGO_SECURE_SSL_REDIRECT` | No | `true` to force HTTPS. | `true` |

---

## Database

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DATABASE_URL` | **PostgreSQL** | Full DB URL to use PostgreSQL. If unset, SQLite is used. | `postgres://user:pass@localhost:5432/fdms` |

---

## Redis / Celery / Channels

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `CELERY_BROKER_URL` | **Celery** | Redis URL for Celery broker. | `redis://127.0.0.1:6379/0` |
| `CELERY_RESULT_BACKEND` | No | Celery result backend. | `redis://127.0.0.1:6379/0` |
| `CELERY_TASK_ALWAYS_EAGER` | No | `true` = run tasks synchronously (testing). | `false` |
| `REDIS_URL` | **Channels** | Redis URL for Channels layer (WebSockets). | `redis://localhost:6379/0` |

---

## FDMS (ZIMRA fiscal device)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `FDMS_ENV` | No | `TEST` or `PROD`. | `PROD` |
| `FDMS_BASE_URL` | **Production** | FDMS API base URL. Production: `https://fdmsapi.zimra.co.zw` (Swagger: `https://fdmsapi.zimra.co.zw/swagger/index.html`). | `https://fdmsapi.zimra.co.zw` |
| `FDMS_DEVICE_ID` | **Production** | Registered device ID. | `12345` |
| `FDMS_DEVICE_SERIAL_NO` | **Production** | Device serial number. | From ZIMRA |
| `FDMS_ACTIVATION_KEY` | **Production** | Device activation key. | From ZIMRA |
| `FDMS_DEVICE_MODEL_NAME` | No | Model name. Default: `Server` | `Server` |
| `FDMS_DEVICE_MODEL_VERSION` | No | Model version. Default: `v1` | `v1` |
| `FDMS_ENCRYPTION_KEY` | Optional | Fernet key (base64) to encrypt private keys at rest. | From `cryptography.fernet.Fernet.generate_key()` |
| `ZIMRA_QR_URL` | No | Verification portal URL for QR code and URL on invoices. Production: `https://fdms.zimra.co.zw`. Default: `https://fdms.zimra.co.zw`. | `https://fdms.zimra.co.zw` |

---

## QuickBooks (legacy / fiscal app)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `QB_CLIENT_ID` | If using legacy QB | Intuit app client ID. | From developer.intuit.com |
| `QB_CLIENT_SECRET` | If using legacy QB | Intuit app client secret. | From developer.intuit.com |
| `QB_REDIRECT_URI` | If using legacy QB | OAuth redirect URI. | `https://takatel.tech/...` |
| `QB_WEBHOOK_VERIFIER` | **Webhooks** | Webhook verifier token (HMAC). Required for `/qb/webhook/` and `/api/qb/webhook/`. | From Intuit app webhook config |

**Note:** The app uses per-tenant OAuth tokens only. Do not use global `QB_REALM_ID` / `QB_ACCESS_TOKEN`; they have been removed from settings.

---

## QuickBooks OAuth2 (quickbooks app)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `QUICKBOOKS_CLIENT_ID` | **OAuth2** | Intuit app client ID. | From developer.intuit.com |
| `QUICKBOOKS_CLIENT_SECRET` | **OAuth2** | Intuit app client secret. | From developer.intuit.com |
| `QUICKBOOKS_REDIRECT_URI` | No | Callback URL (default: `https://takatel.tech/qb/callback/`). | `https://takatel.tech/qb/callback/` |
| `QUICKBOOKS_ENVIRONMENT` | No | `production` or `sandbox`. | `production` |

---

## Multi-tenant (tenant keys)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `TENANT_KEYS_BASE_PATH` | Optional | Base path for tenant private/public keys (e.g. outside repo). | `/var/secrets/tenants` |

---

## Optional (management commands / staging / production profile)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `BACKUP_DIR` | No | Default backup output directory (`backup_db` command). | `/var/backups/fdms` |
| `BACKUP_RETAIN_DAYS` | No | Days to retain backups. Default: `7`. | `7` |
| `PG_DUMP_PATH` | No | Path to `pg_dump` if not on PATH. | `/usr/bin/pg_dump` |
| `SYNC_TARGET_DATABASE_URL` | No | Target DB URL for `sync_to_remote_db`. | `postgres://...` |
| `GUNICORN_ACCESS_LOG` | No | Gunicorn access log path. | `-` or path |
| `GUNICORN_ERROR_LOG` | No | Gunicorn error log path. | `-` or path |
| `LOGS_DIR` | No | Log directory (used in `settings_production`). | `/var/log/fdms` |
| `SECRET_KEY` | **Production** | Used by `settings_production` (not `DJANGO_SECRET_KEY`). | Long random string |
| `ALLOWED_HOSTS` | No | Used by `settings_production` / `settings_staging`. | Comma-separated |
| `DEBUG` | No | Used by staging. | `false` |
| `DB_PATH` | No | SQLite path in production/staging when not using PostgreSQL. | Path |

---

## Minimal production (takatel.tech)

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=takatel.tech,www.takatel.tech`
- `DATABASE_URL` (PostgreSQL)
- `CELERY_BROKER_URL`, `REDIS_URL`
- `FDMS_BASE_URL`, `FDMS_DEVICE_ID`, `FDMS_DEVICE_SERIAL_NO`, `FDMS_ACTIVATION_KEY` (if using FDMS)
- `QB_WEBHOOK_VERIFIER` (if using QuickBooks webhooks)
- `QUICKBOOKS_CLIENT_ID`, `QUICKBOOKS_CLIENT_SECRET` (if using QuickBooks OAuth2)
- `DJANGO_SECURE_SSL_REDIRECT=true` (recommended for HTTPS)
