# Tenant Access Control — Migration Instructions

This document describes how to apply the secure user–tenant access control and backfill existing users.

## 1. Apply the migration

From the project root (the directory containing `manage.py`):

```bash
python manage.py migrate tenants
```

This applies `tenants.0002_user_tenant_m2m`, which adds the `Tenant.users` ManyToMany field (table `tenants_tenant_users`).

## 2. Auto-tenant on user creation

When a **new user** is created:

- **A tenant is created automatically** and the user is assigned to it (slug/name from username, next free `device_id`), **unless**:
  - The user was created by a **company admin** (a staff user in Django admin): then no tenant is created; the admin assigns the user to a tenant in the Tenant form.
  - The user was created by a management command that assigns tenants itself (e.g. `create_fly_tenants`): then no duplicate tenant is created.

So: self-registration, superuser-created users, or API-created users get one tenant each. Staff-created users in admin do not (admin assigns them to an existing tenant).

## 3. Backfill existing users

After the migration, **existing users may have no tenant**. Options:

**Option A — Backfill command (recommended):**

```bash
python manage.py backfill_tenant_for_users
```

Creates one tenant per user who has no tenants and assigns them to it. Safe to run multiple times (skips users who already have at least one tenant). Use `--dry-run` to list users that would get a tenant.

**Option B — Use create_fly_tenants (if you use fly1/fly2):**

```bash
python manage.py create_fly_tenants
```

This creates or updates tenants `fly1` and `fly2` and their staff users, and **assigns each user to the matching tenant** (`tenant.users.add(user)`).

**Option C — Assign via Django Admin:**

1. Log in as a superuser.
2. Go to **Tenants** → open each tenant.
3. In the **Access** section, add the **Users** who may access that tenant.
4. Save.

**Option D — Data migration (custom):**

If you have many users and a convention (e.g. username = tenant slug), you can run a one-off script or data migration that does:

```python
from django.contrib.auth import get_user_model
from tenants.models import Tenant

User = get_user_model()
for tenant in Tenant.objects.filter(is_active=True):
    user = User.objects.filter(username=tenant.slug).first()
    if user and not tenant.users.filter(pk=user.pk).exists():
        tenant.users.add(user)
```

## 4. Verify

- Log in as a **non-superuser** assigned to one tenant: you should see only that tenant on `/select-tenant/` and be able to open the dashboard when that tenant is in session or sent via `X-Tenant-Slug`.
- Send a request with `X-Tenant-Slug: other-tenant` (a tenant the user is not in): response should be **403 Forbidden**.
- Log in as **superuser**: you should see all tenants on select-tenant and access any tenant via header or session.

## 5. Run tests

```bash
python manage.py test tenants.tests
```

All 19 tests should pass (access control, middleware 403, select-tenant filtering, superuser behavior, exempt paths).
