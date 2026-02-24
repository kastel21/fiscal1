from django.contrib import admin
from .models import OfflineBatchFile, OfflineReceiptQueue, SubmissionAttempt


@admin.register(OfflineReceiptQueue)
class OfflineReceiptQueueAdmin(admin.ModelAdmin):
    list_display = ("id", "receipt", "state", "failure_reason", "created_at")
    list_filter = ("state",)
    readonly_fields = ("receipt", "state", "failure_reason", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OfflineBatchFile)
class OfflineBatchFileAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "receipt_count", "file_checksum", "created_at")
    readonly_fields = ("device", "file_path", "file_checksum", "receipt_count", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(SubmissionAttempt)
class SubmissionAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "receipt", "success", "error_message", "attempt_at")
    list_filter = ("success",)
    readonly_fields = ("queue_entry", "receipt", "success", "response_status_code", "error_message", "attempt_at")

    def has_add_permission(self, request):
        return False
