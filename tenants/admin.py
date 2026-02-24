from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "device_id", "is_active", "current_fiscal_day", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("id", "name", "slug", "is_active")}),
        (_("FDMS device"), {"fields": ("device_id", "device_model", "serial_number")}),
        (_("Keys (filesystem paths)"), {"fields": ("private_key_path", "public_key_path")}),
        (_("Fiscal state"), {"fields": ("current_fiscal_day", "previous_hash")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )
