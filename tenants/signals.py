"""
Signals for tenant auto-creation and user-tenant linking.
When a staff user creates a user in admin (company admin), we record it and skip auto-tenant.
"""

import logging
from contextvars import ContextVar

from django.conf import settings
from django.db.models import Max
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify

from .models import Tenant, UserCreationRecord

logger = logging.getLogger(__name__)

# Set by custom UserAdmin when a staff user creates a user; read in post_save to skip auto-tenant.
_creating_user_ctx: ContextVar = ContextVar("tenant_creating_user", default=None)
# Set by management commands (e.g. create_fly_tenants) that assign tenant themselves.
_skip_auto_tenant_ctx: ContextVar = ContextVar("skip_auto_tenant", default=False)


def set_skip_auto_tenant(skip: bool = True):
    """Set to True in management commands that create users and assign tenants themselves."""
    _skip_auto_tenant_ctx.set(skip)


def get_skip_auto_tenant() -> bool:
    return _skip_auto_tenant_ctx.get(False)


def set_creating_user(user):
    """Set the user who is creating another user (e.g. company admin). Call from admin save_model."""
    _creating_user_ctx.set(user)


def clear_creating_user():
    """Clear after save. Call from admin save_model."""
    try:
        _creating_user_ctx.set(None)
    except LookupError:
        pass


def get_creating_user():
    """Return the user who is creating (if any). Used in post_save."""
    return _creating_user_ctx.get(None)


def _next_device_id():
    """Return next available device_id for a new tenant."""
    agg = Tenant.objects.aggregate(Max("device_id"))
    max_id = agg.get("device_id__max")
    base = 50000 if max_id is None else int(max_id) + 1
    while Tenant.objects.filter(device_id=base).exists():
        base += 1
    return base


def _create_tenant_for_user(user):
    """
    Create a tenant for the user and add them to it.
    Slug/name derived from username; device_id is next available.
    """
    base_slug = slugify(user.username) or f"user-{user.pk}"
    slug = base_slug
    suffix = 0
    while Tenant.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base_slug}-{suffix}"
    name = user.get_full_name() or user.username or slug
    device_id = _next_device_id()
    tenant = Tenant.objects.create(
        name=name,
        slug=slug,
        device_id=device_id,
        is_active=True,
    )
    tenant.users.add(user, through_defaults={"role": "user"})
    logger.info("Auto-created tenant slug=%s device_id=%s for user %s", slug, device_id, user.username)
    return tenant


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def maybe_create_tenant_for_user(sender, instance, created, **kwargs):
    """
    When a new user is created, create a tenant and assign them to it, unless:
    - Skip flag is set (e.g. management command that assigns tenant itself), or
    - Creating user is a staff (company admin); we record it and skip (admin will assign tenant), or
    - They already have at least one tenant (e.g. assigned by create_fly_tenants or admin).
    """
    if not created:
        return
    if get_skip_auto_tenant():
        return
    creating = get_creating_user()
    if creating is not None and getattr(creating, "is_staff", False):
        UserCreationRecord.objects.get_or_create(
            user=instance,
            defaults={"created_by": creating},
        )
        logger.info("Skipping auto-tenant for user %s (created by company admin %s)", instance.username, creating.username)
        return
    # Already has tenant(s) — do not create another
    if instance.tenants.exists():
        return
    _create_tenant_for_user(instance)
