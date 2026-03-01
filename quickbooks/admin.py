"""Admin for quickbooks app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import QuickBooksToken


@admin.register(QuickBooksToken)
class QuickBooksTokenAdmin(admin.ModelAdmin):
    list_display = ("realm_id", "user", "is_active", "expires_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("realm_id", "user__username")
    readonly_fields = ("created_at", "updated_at", "access_token_preview", "refresh_token_preview")
    fields = (
        "user",
        "realm_id",
        "access_token_preview",
        "refresh_token_preview",
        "token_type",
        "expires_at",
        "is_active",
        "created_at",
        "updated_at",
    )

    def access_token_preview(self, obj):
        if not obj.access_token:
            return "(empty)"
        return format_html("<code>{}…</code>", (obj.access_token[:20] if len(obj.access_token) > 20 else obj.access_token))

    access_token_preview.short_description = "Access token"

    def refresh_token_preview(self, obj):
        if not obj.refresh_token:
            return "(empty)"
        return format_html("<code>{}…</code>", (obj.refresh_token[:20] if len(obj.refresh_token) > 20 else obj.refresh_token))

    refresh_token_preview.short_description = "Refresh token"
