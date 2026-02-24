"""
Multi-tenant SaaS: Tenant model for shared-database isolation.
Each tenant = one company/business with its own FDMS device_id, keys, and fiscal chain.
"""

import uuid

from django.db import models


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
