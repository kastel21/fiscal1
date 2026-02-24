# Phase 10 — Production Deployment

## 1. Staging Environment

Use the staging settings module for pre-production testing:

```bash
export DJANGO_SETTINGS_MODULE=fdms_project.settings_staging
# Or on Windows:
set DJANGO_SETTINGS_MODULE=fdms_project.settings_staging
```

- **Database:** `db_staging.sqlite3` (separate from dev/prod)
- **FDMS API:** Test/sandbox URL (`https://fdmsapitest.zimra.co.zw` by default)
- **Log rotation:** 10 MB per file, 30 backups (INFO), 90 backups (ERROR)

Configure via environment:

| Variable | Description |
|----------|-------------|
| `FDMS_DEVICE_ID` | Staging device ID |
| `FDMS_DEVICE_SERIAL_NO` | Staging device serial |
| `FDMS_ACTIVATION_KEY` | Staging activation key |
| `ALLOWED_HOSTS` | Comma-separated hosts |
| `FDMS_BASE_URL` | Override FDMS API URL |

## 2. Production Environment

```bash
export DJANGO_SETTINGS_MODULE=fdms_project.settings_production
export SECRET_KEY="your-secret-key"
export ALLOWED_HOSTS="your-domain.com,www.your-domain.com"
export FDMS_BASE_URL="https://fdmsapi.zimra.co.zw"  # Production URL
export FDMS_DEVICE_ID=...
export FDMS_DEVICE_SERIAL_NO=...
export FDMS_ACTIVATION_KEY=...
export FDMS_ENCRYPTION_KEY="..."  # Fernet key for private key encryption
```

## 3. Separate Certs Per Environment

**Critical:** Never use production device certs in staging or development.

- **Staging:** Register a separate FDMS device for staging. Use `FDMS_DEVICE_ID`, `FDMS_DEVICE_SERIAL_NO`, `FDMS_ACTIVATION_KEY` for staging only.
- **Production:** Register a production device with ZIMRA. Store credentials in environment variables; never in code.
- Device certificates and private keys are stored in the database per device. Each environment has its own database and its own registered device(s).

## 4. DB Backup Strategy

### Automated Backups

```bash
# Backup (SQLite)
python manage.py backup_db

# Backup to custom directory, retain 14 days
python manage.py backup_db --output-dir /var/backups/fdms --retain 14
```

**Environment variables:**
- `BACKUP_DIR` — Backup directory (default: `./backups`)
- `BACKUP_RETAIN_DAYS` — Number of backups to retain (default: 7)

### SQLite
- Copies `db.sqlite3` (or `db_staging.sqlite3` / `db_production.sqlite3`) to `backups/db_YYYYMMDD_HHMMSS.sqlite3`
- Prunes backups older than retention policy

### PostgreSQL
- Runs `pg_dump` to `backups/db_YYYYMMDD_HHMMSS.sql`
- Requires PostgreSQL client tools (`pg_dump`) installed
- Set `DATABASE_URL` for production PostgreSQL

### Cron Example

```cron
# Daily backup at 02:00
0 2 * * * cd /opt/fdms && DJANGO_SETTINGS_MODULE=fdms_project.settings_production python manage.py backup_db --retain 14
```

## 5. Rollback Plan

### Application Rollback

1. **Stop the application** (e.g. stop gunicorn/uwsgi)
2. **Deploy previous version** from Git or release artifact:
   ```bash
   git checkout <previous-tag>
   # Or restore from deployment package
   ```
3. **Restore database** if schema or data changed:
   ```bash
   # SQLite
   cp /var/backups/fdms/db_YYYYMMDD_HHMMSS.sqlite3 /opt/fdms/db_production.sqlite3

   # PostgreSQL
   psql -U user -d fdms < /var/backups/fdms/db_YYYYMMDD_HHMMSS.sql
   ```
4. **Run migrations** if rolling back to older schema:
   ```bash
   python manage.py migrate fiscal <migration_number>
   ```
5. **Restart application**

### FDMS-Specific Rollback

- **CloseDay in progress:** Wait for FDMS to complete; do not interrupt. If CloseDay fails, re-run after resolving.
- **Receipt submission errors:** Check FDMS logs; re-sync device with `POST /api/re-sync/` if needed.
- **Certificate issues:** Use IssueCertificate flow for renewal; do not re-register unless necessary.

## 6. Log Retention

| Environment | Handler | Max Size | Backups | Retention |
|-------------|---------|----------|---------|-----------|
| Staging/Prod | fdms.log | 10 MB | 30 | ~30 files |
| Staging/Prod | fdms_json.log | 10 MB | 30 | ~30 files |
| Staging/Prod | fdms_error.log | 5 MB | 90 | ~90 files |
| Staging/Prod | fdms_error_json.log | 5 MB | 90 | ~90 files |

Logs are in `logs/` by default. Override with `LOGS_DIR` in production.

## 7. Before Go-Live Checklist

Run the pre-go-live command:

```bash
python manage.py pre_golive_check
```

This verifies:

1. **Close test fiscal day** — If a fiscal day is open, the command warns and can attempt CloseDay. Wait until status is `FiscalDayClosed` before proceeding.
2. **Submit test receipts** — At least 1 receipt (configurable with `--min-receipts N`)
3. **Run integrity audit** — Validates receipt chain, hashes, and signatures

**Options:**
- `--skip-close` — Do not attempt CloseDay (manual close required)
- `--min-receipts N` — Minimum receipts expected (default: 1)

**Exit code:** 0 = pass, 1 = fail. Use in CI/CD:

```bash
python manage.py pre_golive_check || exit 1
```

## 8. Deployment Order

1. Deploy to **staging** with `settings_staging`
2. Register staging device, open fiscal day, submit test receipts
3. Close staging fiscal day
4. Run `python manage.py pre_golive_check` on staging
5. Run `python manage.py audit_fiscal_integrity` — must pass
6. Run `python manage.py backup_db` — take backup before prod deploy
7. Deploy to **production** with `settings_production`
8. Register production device (if not already)
9. Run `python manage.py pre_golive_check` on production
10. Schedule daily backups via cron
