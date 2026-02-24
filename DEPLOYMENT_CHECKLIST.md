# FDMS SaaS — Production Deployment Checklist (DigitalOcean / Ubuntu 22.04)

Use this checklist for every production deployment. Do not skip steps.

---

## 1. Environment variables (required)

Set these **before** starting the app. Prefer a non-committed file (e.g. `/etc/fdms/env`) or systemd/supervisor environment.

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SETTINGS_MODULE` | **Yes** | Must be `fdms_project.settings_production` |
| `SECRET_KEY` | **Yes** | Long random string (e.g. `openssl rand -base64 48`) |
| `ALLOWED_HOSTS` | **Yes** | Comma-separated (e.g. `example.com,www.example.com`) |
| `DATABASE_URL` | **Yes** (PostgreSQL) | `postgres://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require` |
| `FDMS_BASE_URL` | **Yes** | Production FDMS API base URL |
| `FDMS_DEVICE_ID` | If using global device | Device ID (production device only) |
| `FDMS_DEVICE_SERIAL_NO` | If using global device | Device serial |
| `FDMS_ACTIVATION_KEY` | If using global device | Activation key |
| `CELERY_BROKER_URL` | **Yes** (Celery) | e.g. `redis://127.0.0.1:6379/0` |
| `CELERY_RESULT_BACKEND` | **Yes** (Celery) | Same Redis URL |
| `TENANT_KEYS_BASE_PATH` | Recommended | Base path for tenant private keys (e.g. `/var/secrets/tenants`) |

Optional: `LOGS_DIR`, `DJANGO_STATIC_ROOT`, `DJANGO_MEDIA_ROOT`, `DJANGO_MEDIA_URL`, QB_* for QuickBooks.

---

## 2. Run migrations

```bash
export DJANGO_SETTINGS_MODULE=fdms_project.settings_production
# Set SECRET_KEY, ALLOWED_HOSTS, DATABASE_URL, FDMS_BASE_URL (and any others) first

python manage.py migrate
python manage.py migrate django_celery_beat
```

Resolve any migration conflicts before starting the app.

---

## 3. Collect static files

```bash
export DJANGO_SETTINGS_MODULE=fdms_project.settings_production
# Ensure STATIC_ROOT is set (default: staticfiles in project root)

python manage.py collectstatic --noinput
```

Point Nginx `location /static/` to the same path as `STATIC_ROOT` (e.g. `/var/www/fdms/staticfiles/`).

---

## 4. Pre-deploy safety check

```bash
export DJANGO_SETTINGS_MODULE=fdms_project.settings_production
# All required env vars set

python manage.py check --deploy
```

Fix every reported issue. Do not deploy if this command reports errors or critical warnings.

---

## 5. Test Celery (worker + beat)

```bash
# Terminal 1 — worker
export DJANGO_SETTINGS_MODULE=fdms_project.settings_production
celery -A fdms_project worker -l info --concurrency=2

# Terminal 2 — beat (after worker is running)
export DJANGO_SETTINGS_MODULE=fdms_project.settings_production
celery -A fdms_project beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Trigger a task (e.g. from Django shell):

```python
from fiscal.tasks import run_fdms_ping
run_fdms_ping.delay()
```

Confirm the worker logs the task and that no import/runtime errors occur. Stop workers when done testing.

---

## 6. Verify tenant isolation

- Send a request **with** `X-Tenant-Slug: <tenant_a_slug>` and confirm responses only contain data for that tenant (devices, receipts, logs).
- Send a request **with** `X-Tenant-Slug: <tenant_b_slug>` and confirm different data (no overlap with tenant A).
- Confirm exempt paths (e.g. `/admin/`, `/health/`) do not require the header and do not leak tenant data to unauthenticated users.

Use staff/superuser and API or UI list/detail endpoints for devices and receipts.

---

## 7. Confirm FDMS Ping working

- Ensure Celery worker and beat are running with production settings.
- Confirm the periodic task **FDMS Ping (all tenants) every 5 min** is enabled in Django Admin → Periodic Tasks (django_celery_beat).
- Check logs: `tail -f /var/log/fdms/celery_worker.log` (or your LOGS_DIR) for `FDMS ping success` or `FDMS ping failed` with tenant/device_id.
- Optional: run once manually: `python manage.py shell` → `from fiscal.tasks import run_fdms_ping; run_fdms_ping.delay()` and confirm worker processes it.

---

## 8. Confirm SSL active (production)

- Serve the app behind Nginx (or another reverse proxy) with TLS.
- Ensure Nginx uses `listen 443 ssl` and valid certificates (e.g. Let’s Encrypt).
- Ensure production settings have `SECURE_SSL_REDIRECT = True`, `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, and HSTS headers.
- In the browser, open `https://example.com` and confirm:
  - No mixed content warnings.
  - Cookie flags show Secure where expected (dev tools).
  - Redirect from `http://` to `https://` works.

---

## 9. Confirm DEBUG off

- With production settings and env loaded, run:

  ```bash
  python -c "
  import os
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fdms_project.settings_production')
  import django
  django.setup()
  from django.conf import settings
  assert not settings.DEBUG, 'DEBUG must be False in production'
  print('DEBUG is False')
  "
  ```

- If the app starts with `fdms_project.settings_production`, the startup check in that module will raise `RuntimeError` if `DEBUG` is True. So a running app implies DEBUG is False unless overridden later (do not override).

---

## 10. Supervisor (after config installed)

```bash
sudo cp deploy/supervisor/fdms.conf /etc/supervisor/conf.d/fdms.conf
# Edit paths/user/env in fdms.conf to match your server

sudo mkdir -p /var/log/fdms
sudo chown www-data:www-data /var/log/fdms

sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl status
```

All three programs (fdms_gunicorn, fdms_celery_worker, fdms_celery_beat) should be running.

---

## 11. Nginx (after config installed)

```bash
sudo cp deploy/nginx/fdms /etc/nginx/sites-available/fdms
# Edit server_name and paths (static/media) and SSL blocks

sudo ln -s /etc/nginx/sites-available/fdms /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 12. Database backups

- Schedule `scripts/backup_db.sh` (e.g. daily via cron). Ensure `DATABASE_URL` is set in the cron environment.
- Example cron (daily at 02:00):  
  `0 2 * * * cd /var/www/fdms && DATABASE_URL="..." ./scripts/backup_db.sh /var/backups/fdms`
- Retain backups according to policy (script default: 14 days).

---

## Quick reference: deployment order

1. Set all required environment variables.
2. `python manage.py check --deploy` and fix issues.
3. `python manage.py migrate` (and django_celery_beat).
4. `python manage.py collectstatic --noinput`.
5. Install and start Gunicorn (e.g. via Supervisor).
6. Install and start Celery worker and beat (e.g. via Supervisor).
7. Install Nginx config, point domain, enable SSL, reload Nginx.
8. Verify tenant isolation, FDMS Ping, SSL, and DEBUG off (sections 6–9).
9. Schedule database backups (section 12).
