# Celery FDMS Ping — Production Setup

## Overview

- **run_fdms_ping**: Runs every 5 minutes (django-celery-beat). Acquires a Redis lock to prevent overlap. Enqueues **ping_single_tenant** for each active tenant.
- **ping_single_tenant(tenant_id)**: Loads tenant, resolves device via **get_device_for_tenant**, calls **send_ping(tenant)** (reuses **DeviceApiService().ping(device)**). Never crashes the loop; logs success/failure per tenant.

## 1. Install

```bash
pip install -r requirements.txt
```

Requirements include: `celery`, `redis`, `django-celery-beat`.

## 2. Configure Celery

- **fdms_project/celery.py**: Already configured; broker and autodiscover from settings.
- **fdms_project/__init__.py**: Loads `celery_app` so `@shared_task` works.

Settings (fdms_project/settings.py):

- `CELERY_BROKER_URL`: `redis://127.0.0.1:6379/0`
- `CELERY_RESULT_BACKEND`: same Redis or separate DB
- `CELERY_BEAT_SCHEDULER`: `django_celery_beat.schedulers:DatabaseScheduler`

## 3. Migrations

```bash
python manage.py migrate django_celery_beat
python manage.py migrate fiscal
```

Migration **0033_add_fdms_ping_beat_schedule** creates:

- Interval: every 5 minutes
- PeriodicTask: **fiscal.run_fdms_ping** (enabled)

If **django_celery_beat** has no migration named **0001_initial**, edit **fiscal/migrations/0033_add_fdms_ping_beat_schedule.py** and set `dependencies` to your actual latest django_celery_beat migration.

## 4. Beat scheduling (django-celery-beat)

Schedule is created by migration 0033. To verify or edit:

- Django Admin → **Periodic Tasks** → **Periodic tasks**
- Or: **Interval schedules** (5 minutes) and **Periodic tasks** (task: **fiscal.run_fdms_ping**)

## 5. Logging

- **run_fdms_ping**: Logs "FDMS ping scheduled for N tenant(s)" and "FDMS ping skipped: previous run still active" when lock is held.
- **ping_single_tenant**: Logs with **extra**:
  - `tenant_id`, `tenant_slug`, `tenant_name`, `device_id`, `success`, `error` (and `reporting_frequency`, `operation_id` on success).

Use a logging handler that supports **extra** (e.g. JSON formatter) for production. No `print()` in tasks.

## 6. Supervisor (production)

1. Create log directory and app directory:

   ```bash
   sudo mkdir -p /var/log/celery
   sudo chown www-data:www-data /var/log/celery
   ```

2. Copy config (adjust paths and user):

   ```bash
   sudo cp deploy/supervisor/celery.conf /etc/supervisor/conf.d/celery.conf
   ```

3. Edit **/etc/supervisor/conf.d/celery.conf**:
   - Set `command` to your venv path, e.g. `/var/www/fdms/venv/bin/celery`
   - Set `directory` to your project root, e.g. `/var/www/fdms`
   - Set `user` if not `www-data`
   - Set `environment` if you use env vars for broker/settings

4. Reload and start:

   ```bash
   sudo supervisorctl reread
   sudo supervisorctl update
   sudo supervisorctl start celery_worker celery_beat
   sudo supervisorctl status
   ```

## 7. Safety

- **Overlap**: Redis lock `fdms:ping:run_fdms_ping` with 300s TTL; if a run is still active, the next beat run skips (logs "skipped_lock").
- **DB connections**: Each task calls `connection.close()` in `finally` so connections are not held.
- **Timeout**: FDMS HTTP calls use existing timeout (e.g. 30s) in device_api; no change to FDMS logic.
- **Duplication**: Lock prevents overlapping **run_fdms_ping**; per-tenant work is one **ping_single_tenant** per tenant per cycle.
- **Tenant isolation**: Each **ping_single_tenant** loads one tenant by ID and uses **send_ping(tenant)** (device resolved per tenant).

## 8. Testing

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Worker
celery -A fdms_project worker -l info

# Terminal 3: Beat
celery -A fdms_project beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Trigger once (no wait for beat):

```bash
python manage.py shell -c "
from fiscal.tasks import run_fdms_ping
print(run_fdms_ping())
"
```

Or enqueue:

```bash
python manage.py shell -c "
from fiscal.tasks import run_fdms_ping
run_fdms_ping.delay()
"
```

## 9. Production checklist

- [ ] Redis running and `CELERY_BROKER_URL` correct
- [ ] `python manage.py migrate django_celery_beat` and `migrate` applied
- [ ] Periodic task "FDMS Ping (all tenants) every 5 min" exists and is enabled (Admin or migration 0033)
- [ ] Supervisor: **celery_worker** and **celery_beat** running
- [ ] Log dir `/var/log/celery` (or your choice) exists and is writable
- [ ] No `CELERY_TASK_ALWAYS_EAGER=true` in production
- [ ] Each active tenant has a registered **FiscalDevice** (with `tenant_id` set) so **send_ping(tenant)** can resolve device
