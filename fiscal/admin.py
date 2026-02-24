from django.conf import settings
from django.contrib import admin

from .admin_mixins import TenantAdminMixin
from .models import Company, CreditNoteImport, Customer, FDMSApiLog, FDMSConfigs, FiscalDay, FiscalDevice, FiscalEditAttempt, InvoiceImport, Product, QuickBooksConnection, QuickBooksEvent, QuickBooksInvoice, Receipt, TaxMapping


@admin.register(Company)
class CompanyAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "tin", "currency_default", "created_at")
    search_fields = ("name", "tin")


@admin.register(Customer)
class CustomerAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "tin", "phone", "email", "is_active", "company")
    list_filter = ("is_active", "company")
    search_fields = ("name", "tin", "email")


@admin.register(TaxMapping)
class TaxMappingAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("local_code", "display_name", "fdms_tax_id", "fdms_tax_code", "tax_percent", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("local_code", "display_name")


@admin.register(Product)
class ProductAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "price", "tax_percent", "hs_code", "is_active", "company")
    list_filter = ("is_active", "company")
    search_fields = ("name", "hs_code")


@admin.register(FiscalDevice)
class FiscalDeviceAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = (
        "device_id",
        "is_registered",
        "fiscal_day_status",
        "last_fiscal_day_no",
        "last_receipt_global_no",
        "updated_at",
    )
    search_fields = ("device_id",)

    def delete_queryset(self, request, queryset):
        """Bulk delete devices one-by-one so pre_delete cascade (FDMSConfigs) runs."""
        for obj in queryset:
            obj.delete()


@admin.register(FiscalDay)
class FiscalDayAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("device", "fiscal_day_no", "status", "opened_at", "closed_at")
    list_filter = ("status",)


class ReceiptAdjustmentInline(admin.TabularInline):
    """List credit/debit notes that reference this receipt as original_invoice."""
    model = Receipt
    fk_name = "original_invoice"
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("receipt_global_no", "document_type", "invoice_no", "reason_short", "receipt_total", "created_at")
    readonly_fields = ("receipt_global_no", "document_type", "invoice_no", "reason_short", "receipt_total", "created_at")

    def reason_short(self, obj):
        if not obj.reason:
            return ""
        return (obj.reason[:40] + "…") if len(obj.reason) > 40 else obj.reason

    reason_short.short_description = "Reason"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Receipt)
class ReceiptAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "device",
        "receipt_global_no",
        "document_type",
        "invoice_no",
        "original_invoice",
        "reason_short",
        "receipt_total",
        "receipt_type",
        "created_at",
    )
    list_filter = ("document_type", "receipt_type", "device")
    search_fields = ("invoice_no", "original_invoice_no")
    readonly_fields = (
        "device",
        "fiscal_day_no",
        "receipt_global_no",
        "receipt_counter",
        "currency",
        "receipt_taxes",
        "receipt_lines",
        "receipt_payments",
        "receipt_type",
        "invoice_no",
        "original_invoice_no",
        "original_receipt_global_no",
        "receipt_date",
        "receipt_total",
        "fdms_receipt_id",
        "created_at",
    )
    inlines = [ReceiptAdjustmentInline]

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)

    def reason_short(self, obj):
        if not obj.reason:
            return ""
        return (obj.reason[:50] + "…") if len(obj.reason) > 50 else obj.reason

    reason_short.short_description = "Reason"


@admin.register(CreditNoteImport)
class CreditNoteImportAdmin(admin.ModelAdmin):
    list_display = ("id", "original_receipt", "credit_total", "remaining_balance_before", "user_confirmed", "created_at")
    list_filter = ("user_confirmed",)
    readonly_fields = ("original_receipt", "parsed_lines", "original_invoice_snapshot", "remaining_balance_before", "credit_total", "credit_reason", "user_confirmed", "created_at", "credit_note_receipt")

    def has_add_permission(self, request):
        return False


@admin.register(InvoiceImport)
class InvoiceImportAdmin(admin.ModelAdmin):
    list_display = ("id", "sheet_name", "receipt_type", "currency", "user_confirmed", "created_at")
    list_filter = ("receipt_type",)
    readonly_fields = ("sheet_name", "header_row", "parsed_lines", "receipt_type", "currency", "tax_id", "user_confirmed", "created_at", "fiscal_receipt")

    def has_add_permission(self, request):
        return False


@admin.register(QuickBooksConnection)
class QuickBooksConnectionAdmin(admin.ModelAdmin):
    list_display = ("realm_id", "company_name", "is_active", "token_expires_at", "updated_at")
    list_filter = ("is_active",)
    readonly_fields = ("realm_id", "token_expires_at", "created_at", "updated_at")


@admin.register(QuickBooksEvent)
class QuickBooksEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "created_at")
    readonly_fields = ("event_type", "payload", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(QuickBooksInvoice)
class QuickBooksInvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "qb_invoice_id", "fiscalised", "fiscal_receipt", "fiscal_error", "created_at")
    list_filter = ("fiscalised",)
    search_fields = ("qb_invoice_id",)
    readonly_fields = ("qb_invoice_id", "qb_customer_id", "currency", "total_amount", "raw_payload", "fiscal_receipt", "fiscal_error", "created_at", "updated_at")


@admin.register(FiscalEditAttempt)
class FiscalEditAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "receipt", "source", "blocked", "diff_summary", "created_at")
    list_filter = ("blocked", "source")
    readonly_fields = ("receipt", "original_snapshot", "attempted_change", "source", "actor", "blocked", "diff_summary", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(FDMSConfigs)
class FDMSConfigsAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("device_id", "fetched_at", "allowed_currencies")
    list_filter = ("device_id",)
    readonly_fields = ("raw_response", "tax_table", "allowed_currencies", "fetched_at")


@admin.register(FDMSApiLog)
class FDMSApiLogAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("endpoint", "method", "status_code", "operation_id", "created_at")
    list_filter = ("method",)
    search_fields = ("operation_id", "endpoint", "error_message")

    def has_add_permission(self, request):
        return settings.DEBUG

    def has_change_permission(self, request, obj=None):
        return settings.DEBUG

    def has_delete_permission(self, request, obj=None):
        return settings.DEBUG
