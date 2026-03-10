from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Tenant, UserCreationRecord, UserTenant
from .signals import clear_creating_user, set_creating_user

User = get_user_model()


class UserTenantInline(admin.TabularInline):
    model = UserTenant
    extra = 0
    raw_id_fields = ("user",)
    autocomplete_fields = ()  # user has no search_fields by default; use raw_id


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "device_id", "is_active", "current_fiscal_day", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (UserTenantInline,)
    fieldsets = (
        (None, {"fields": ("id", "name", "slug", "is_active")}),
        (_("FDMS device"), {"fields": ("device_id", "device_model", "serial_number")}),
        (_("Keys (filesystem paths)"), {"fields": ("private_key_path", "public_key_path")}),
        (_("Fiscal state"), {"fields": ("current_fiscal_day", "previous_hash")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )


class CustomUserAdmin(BaseUserAdmin):
    """Record when a staff user (company admin) creates a user so we skip auto-tenant creation."""

    def save_model(self, request, obj, form, change):
        if not change and getattr(request.user, "is_staff", False):
            set_creating_user(request.user)
        try:
            super().save_model(request, obj, form, change)
        finally:
            clear_creating_user()


@admin.register(UserCreationRecord)
class UserCreationRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "created_by")
    list_filter = ("created_by",)
    search_fields = ("user__username", "created_by__username")
    raw_id_fields = ("user", "created_by")
    readonly_fields = ("user", "created_by")


@admin.register(UserTenant)
class UserTenantAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "created_at")
    list_filter = ("tenant", "role")
    search_fields = ("user__username", "tenant__slug", "tenant__name")
    raw_id_fields = ("user", "tenant")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


# Replace default User admin so we can set "created by" when staff creates a user
if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
