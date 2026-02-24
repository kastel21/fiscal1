# FDMS Operations Runbook

Day-to-day operations and troubleshooting for the FDMS Django application.

---

## Daily Operations

### Morning Checklist

1. **Verify device status** – Open `/fdms/dashboard/` and confirm device shows "Registered".
2. **Check fiscal day** – Ensure status is `FiscalDayOpened` before submitting receipts.
3. **Review logs** – Check `/fdms/logs/` for any recent errors.

### Opening a Fiscal Day

1. Go to `/fdms/fiscal/`.
2. Ensure current status is `FiscalDayClosed` or `FiscalDayCloseFailed`.
3. Click **Open Day**.
4. Confirm status changes to `FiscalDayOpened`.

### Submitting Receipts

1. Ensure fiscal day is open.
2. Go to `/fdms/receipts/new/`.
3. Enter receipt type, currency, total, and optional invoice number.
4. Click **Submit Receipt**.
5. Note the receipt global number in the success message.

### Closing a Fiscal Day

1. Go to `/fdms/fiscal/`.
2. Click **Close Day**.
3. Wait for status to change from `FiscalDayCloseInitiated` to `FiscalDayClosed` (polling every 10 seconds; can take several minutes).
4. If status becomes `FiscalDayCloseFailed`, check closing error code and logs.

---

## Backups

### Manual Backup

```bash
python manage.py backup_db
```

### Automated Backup (Cron)

```cron
0 2 * * * cd /opt/fdms && DJANGO_SETTINGS_MODULE=fdms_project.settings_production python manage.py backup_db --retain 14
```

Backups are stored in `backups/` by default. Override with `--output-dir` or `BACKUP_DIR`.

---

## Integrity Audit

### Run Audit

```bash
python manage.py audit_fiscal_integrity
```

Or use the web UI: `/fdms/audit/` → **Run Audit**.

### Pre-Go-Live Check

```bash
python manage.py pre_golive_check
```

Verifies: fiscal day closed, test receipts submitted, integrity audit passes. Exit code 0 = pass.

---

## Troubleshooting

### Device Not Registered

- Register at `/fdms/device/` with Device ID, Activation Key, Serial No.
- Ensure FDMS test/production API is reachable.

### FDMS Unreachable

- Check network connectivity.
- Verify `FDMS_BASE_URL` is correct.
- Check certificate validity.

### CloseDay Taking Too Long

- CloseDay is async; wait up to 5 minutes.
- Check `/fdms/logs/` for FDMS errors.
- If stuck, contact ZIMRA support with `operationID` from the close response.

### Receipt Submission Fails

- Ensure fiscal day is open.
- Verify `receipt_total` matches sum of lines/taxes.
- Check logs for FDMS error detail.
- Run **Re-sync** (`POST /api/re-sync/`) and retry.

### Hash Mismatch / Chain Errors

- Run `python manage.py audit_fiscal_integrity --verbose`.
- Do not manually edit receipts; chain must remain intact.
- If data corruption suspected, restore from backup and contact support.

### Certificate Expiry

- Run `python manage.py check_certificate_expiry` to list expiring certs.
- Use IssueCertificate flow before expiry (device registration / renewal path).

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DJANGO_SETTINGS_MODULE` | `fdms_project.settings` (dev) / `fdms_project.settings_staging` / `fdms_project.settings_production` |
| `FDMS_BASE_URL` | FDMS API URL |
| `FDMS_DEVICE_ID` | Device ID |
| `FDMS_DEVICE_SERIAL_NO` | Serial number |
| `FDMS_ACTIVATION_KEY` | Activation key |
| `FDMS_ENCRYPTION_KEY` | Fernet key for private key encryption (production) |
| `SECRET_KEY` | Django secret (production) |
| `ALLOWED_HOSTS` | Comma-separated hosts (production) |

---

## Support

- FDMS API docs: ZIMRA FDMS v7.2 specification
- Internal: See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) and [API_REFERENCE.md](API_REFERENCE.md)
