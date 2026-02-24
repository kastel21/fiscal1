"""Admin for legal app."""

from django.contrib import admin

from .models import EulaAcceptance


@admin.register(EulaAcceptance)
class EulaAcceptanceAdmin(admin.ModelAdmin):
    list_display = ("user", "accepted_at")
    list_filter = ("accepted_at",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("accepted_at",)
    date_hierarchy = "accepted_at"
