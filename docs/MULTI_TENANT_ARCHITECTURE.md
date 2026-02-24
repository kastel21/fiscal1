# Multi-Tenant FDMS SaaS Architecture (Text Diagram)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT / LOAD BALANCER                             │
│                     (sends X-Tenant-Slug on every request)                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE                                                                  │
│  TenantResolutionMiddleware: read X-Tenant-Slug → Tenant.objects.get(slug)   │
│  → request.tenant = tenant; set_current_tenant(tenant)                      │
│  Exempt: /admin/, /static/, /media/, /health/                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  TENANTS APP                                                                 │
│  - Tenant model (UUID, slug, device_id, key paths, current_fiscal_day,       │
│    previous_hash, is_active)                                                 │
│  - tenants.middleware.TenantResolutionMiddleware                            │
│  - tenants.context.current_tenant / set_current_tenant                      │
│  - tenants.utils.get_device_for_tenant(tenant)                              │
│  - tenants.managers.TenantScopedManager (optional)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
          ┌────────────────────────────┼────────────────────────────┐
          ▼                             ▼                            ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────────────┐
│  FISCAL APP          │   │  FISCAL APP        │   │  FISCAL APP                 │
│  (FDMS)              │   │  (Receipts)       │   │  (Models)                   │
│  - device_api        │   │  - receipt_service│   │  - FiscalDevice.tenant_id   │
│  - fdms_device_svc   │   │  - close_day       │   │  - Receipt.tenant_id        │
│  - fdms_logger       │   │  - fiscal_day_totals│   │  - FiscalDay.tenant_id      │
│  (device.tenant      │   │  (filter by        │   │  - FDMSApiLog.tenant_id     │
│   passed to log)     │   │   request.tenant   │   │  - FDMSConfigs.tenant_id    │
└─────────────────────┘   └─────────────────────┘   │  - TaxMapping, etc.        │
                                                      └─────────────────────────────┘
          │                             │                            │
          └────────────────────────────┴────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SHARED DATABASE (PostgreSQL)                                                │
│  - tenants_tenant                                                             │
│  - fiscal_fiscaldevice (tenant_id), fiscal_receipt (tenant_id),               │
│    fiscal_fiscalday (tenant_id), fiscal_fdmsapilog (tenant_id), ...          │
│  - Indexes: (tenant_id), (tenant_id, created_at), (tenant_id, fiscal_day_no),│
│    (tenant_id, receipt_global_no)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FDMS SIGNING (per tenant / device)                                          │
│  - Private key: FiscalDevice.private_key_pem (or Tenant.private_key_path)   │
│  - device_id: device.device_id (tenant.device_id when using tenant keys)     │
│  - previous_hash: last receipt for device (chain per device)                 │
│  - Section 13.3 compliant; no change to canonical/signature spec              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Folder Structure (SaaS)

```
fdms_project/
  settings.py          # DEBUG, ALLOWED_HOSTS, SECURE_SSL_REDIRECT from env; TENANT_KEYS_BASE_PATH
  urls.py
  middleware.py        # (tenant middleware lives in tenants app)

tenants/
  models.py            # Tenant (UUID, slug, device_id, key paths, current_fiscal_day, previous_hash)
  admin.py             # TenantAdmin
  middleware.py        # TenantResolutionMiddleware
  context.py           # current_tenant, set_current_tenant, clear_current_tenant
  utils.py             # get_device_for_tenant(tenant)
  managers.py          # TenantScopedManager (optional)

fiscal/
  models.py            # FiscalDevice, Receipt, FiscalDay, FDMSApiLog, ... (all with tenant FK)
  admin.py             # TenantAdminMixin on all tenant-scoped ModelAdmins
  admin_mixins.py      # TenantAdminMixin
  services/
    device_api.py      # passes device.tenant to log_fdms_call
    fdms_device_service.py
    fdms_logger.py     # log_fdms_call(..., tenant=)
    receipt_service.py # (scope by device.tenant in callers)
    close_day_counter_builder.py
    fiscal_day_totals.py
  views.py             # (use get_device_for_tenant(request.tenant) and filter by tenant)
  views_management.py
  views_fdms.py
  views_api.py

dashboard/
  ...                  # (scope metrics/summary by request.tenant)

docs/
  MULTI_TENANT_MIGRATION_STEPS.md
  MULTI_TENANT_ARCHITECTURE.md
```

## Security Summary

- **Isolation**: All tenant-scoped models have `tenant_id`; queries must filter by `request.tenant`.
- **Middleware**: Ensures `request.tenant` is set (or 404) for non-exempt paths.
- **Admin**: TenantAdminMixin filters by `request.tenant` when set; superadmin sees all when tenant is None (admin exempt).
- **FDMS**: Signing and chain remain per device; device is always tied to one tenant.
- **Keys**: Production uses `TENANT_KEYS_BASE_PATH`; store keys outside project directory.
