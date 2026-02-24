# Multi-Tenant Migration Steps

## 1. Run Migrations

```bash
python manage.py migrate tenants
python manage.py migrate fiscal
```

Existing rows will have `tenant_id = NULL`. Backfill in a data migration (see step 3).

## 2. Create Initial Tenant(s)

For each existing company/device, create a Tenant and link it:

```python
from tenants.models import Tenant
from fiscal.models import FiscalDevice

# Example: one tenant per existing device
for device in FiscalDevice.objects.filter(is_registered=True):
    tenant, _ = Tenant.objects.get_or_create(
        slug=f"company-{device.device_id}",
        defaults={
            "name": device.taxpayer_name or f"Tenant {device.device_id}",
            "device_id": device.device_id,
            "device_model": getattr(device, "device_model_name", ""),
            "serial_number": getattr(device, "device_serial_no", ""),
            "current_fiscal_day": device.last_fiscal_day_no,
            "is_active": True,
        },
    )
    device.tenant = tenant
    device.save(update_fields=["tenant_id"])
```

Run a similar backfill for Receipt, FiscalDay, FDMSApiLog, FDMSConfigs, etc., setting `tenant_id` from the related device's tenant.

## 3. Data Migration (Backfill tenant_id)

Create a fiscal data migration that:

1. For each FiscalDevice with `tenant_id` NULL: create or get a Tenant (e.g. by device_id), set device.tenant.
2. For Receipt: set receipt.tenant_id = receipt.device.tenant_id where device.tenant_id is not null.
3. For FiscalDay: set fiscalday.tenant_id = fiscalday.device.tenant_id.
4. For FDMSApiLog: optionally set tenant from endpoint (parse device_id from path) or leave null for old logs.
5. For FDMSConfigs: set tenant from device_id (lookup device then tenant).
6. For Company, Customer, Product, TaxMapping: assign default tenant or leave null until UI assigns.

After backfill, you can make `tenant` non-nullable on critical models (new migration).

## 4. API Usage

All non-exempt requests must send:

```
X-Tenant-Slug: <tenant-slug>
```

Exempt paths (no header required): `/admin/`, `/static/`, `/media/`, `/health/`, `/api/health/`.

## 5. Views / Services Scoping

Ensure every query that reads tenant-scoped data filters by `request.tenant`:

- Replace `FiscalDevice.objects.filter(is_registered=True)` with  
  `FiscalDevice.objects.filter(tenant=request.tenant, is_registered=True)` when tenant is required.
- Use `get_device_for_tenant(request.tenant)` from `tenants.utils` to get the device for the current tenant.
- In views that currently use `get_device_for_request(request)` (session/GET device_id), switch to tenant-scoped device: either require `request.tenant` and use `get_device_for_tenant(request.tenant)`, or keep device_id in session but validate that device.tenant_id == request.tenant.id.

## 6. FDMS Signing (Tenant Keys)

- Signing remains per-device: `device.get_private_key_pem_decrypted()`, `device.device_id`, previous hash from last receipt for that device.
- Optionally support Tenant.private_key_path / public_key_path: when set, load key from filesystem (e.g. `TENANT_KEYS_BASE_PATH + tenant.private_key_path`) and use tenant.device_id for signing. When not set, keep using FiscalDevice certificate_pem/private_key_pem.

## 7. Celery Tasks

In tasks that run without a request (e.g. `ping_devices_task`), resolve tenant per device:

```python
for device in FiscalDevice.objects.filter(is_registered=True).select_related("tenant"):
    if device.tenant_id is None:
        continue
    set_current_tenant(device.tenant)
    try:
        # ... ping(device) ...
    finally:
        clear_current_tenant()
```

## 8. Admin

- Admin is exempt from tenant middleware; `request.tenant` is None. With TenantAdminMixin, querysets are not filtered in admin (superadmin sees all).
- To restrict tenant admins to one tenant: add a UserProfile with tenant FK and in get_queryset filter by request.user.userprofile.tenant when not request.user.is_superuser.

## 9. Production Checklist

- Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_SECURE_SSL_REDIRECT=true` (if HTTPS).
- Set `TENANT_KEYS_BASE_PATH` to a directory outside the project (e.g. `/var/secrets/tenants/`) when using Tenant.private_key_path.
- Ensure PostgreSQL is used and indexes on tenant_id are present (migration 0032 adds them).
