"""
Multi-tenant SaaS: Tenant model for shared-database isolation.
Each tenant = one company/business with its own FDMS device_id, keys, and fiscal chain.
User access is enforced via UserTenant (through model); use user_has_tenant_access() to check.
"""

import uuid

from django.conf import settings
from django.db import models


class UserTenant(models.Model):
    """
    Through model for User–Tenant membership with role.
    Enables request.user.tenants and tenant.users with an explicit role per membership.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_tenant_memberships",
    )
    tenant = models.ForeignKey(
        "Tenant",
        on_delete=models.CASCADE,
        related_name="user_tenant_memberships",
    )
    role = models.CharField(max_length=50, default="user")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants_usertenant"
        verbose_name = "User–tenant membership"
        verbose_name_plural = "User–tenant memberships"
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="tenants_usertenant_user_tenant_uniq"),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.tenant.slug} ({self.role})"


class Tenant(models.Model):
    """
    Tenant (company/business) for multi-tenant FDMS. One FDMS device identity per tenant.
    Keys may be stored on filesystem (private_key_path, public_key_path) or in FiscalDevice (legacy).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True, db_index=True)
    # FDMS device identity (one per tenant)
    device_id = models.IntegerField(unique=True, db_index=True)
    device_model = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=64, blank=True)
    # Key paths (filesystem); leave blank to use FiscalDevice certificate_pem/private_key_pem
    private_key_path = models.CharField(max_length=512, blank=True)
    public_key_path = models.CharField(max_length=512, blank=True)
    # Fiscal chain state (updated atomically on receipt/close day)
    current_fiscal_day = models.IntegerField(null=True, blank=True)
    previous_hash = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Users allowed to access this tenant (via UserTenant through model). Superusers bypass in middleware.
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="tenants",
        blank=True,
        through="UserTenant",
        through_fields=("tenant", "user"),
        help_text="Users who may access this tenant (managed via User–tenant memberships). Superusers can access all.",
    )

    class Meta:
        db_table = "tenants_tenant"
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["device_id"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class UserCreationRecord(models.Model):
    """
    Records who created a user. If created_by is a staff user (company admin),
    we do not auto-create a tenant for the new user; the admin will assign them to a tenant.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="creation_record",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_users",
    )

    class Meta:
        db_table = "tenants_usercreationrecord"
        verbose_name = "User creation record"
        verbose_name_plural = "User creation records"

    def __str__(self):
        return f"Record for {self.user.username}"
