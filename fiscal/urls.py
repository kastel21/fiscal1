"""URL configuration for fiscal app."""

from django.shortcuts import redirect
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from invoices.views import invoice_create_api

from . import views
from . import views_api
from . import views_credit_debit_forms
from . import views_dashboard
from . import views_invoice_import
from . import views_fdms
from . import views_management
from . import views_auth

urlpatterns = [
    path("", lambda r: redirect("fdms_dashboard")),
    path("register/", views.device_register, name="device_register"),
    path("dashboard/", lambda r: redirect("fdms_dashboard")),
    path("api/dashboard/status/", views.dashboard_status_api, name="dashboard_status_api"),
    path("api/fdms/status/", views.api_fdms_status, name="api_fdms_status"),
    path("api/open-day/", views.open_day_api, name="open_day_api"),
    path("api/close-day/", views.close_day_api, name="close_day_api"),
    path("api/submit-receipt/", views.submit_receipt_api, name="submit_receipt_api"),
    path("api/invoices/", invoice_create_api),
    path("api/re-sync/", views.re_sync_api, name="re_sync_api"),
    path("api/verify-taxpayer/", views_fdms.api_verify_taxpayer, name="api_verify_taxpayer"),
    path("api/token/", views_auth.CustomTokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("api/company/", views_management.api_company),
    path("api/config/taxes/", views_management.api_config_taxes),
    path("api/tax-mappings/", views_management.api_tax_mappings_list),
    path("api/tax-mappings/<int:pk>/", views_management.api_tax_mapping_detail),
    path("api/devices/", views_management.api_devices_list),
    path("api/devices/<int:pk>/certificate-status/", views_management.api_device_certificate_status),
    path("api/devices/<int:pk>/open-day/", views_management.api_device_open_day),
    path("api/devices/<int:pk>/close-day/", views_management.api_device_close_day),
    path("api/devices/<int:pk>/ping/", views_management.api_device_ping),
    path("api/devices/<int:pk>/", views_management.api_device_detail),
    path("api/products/", views_management.api_products_list),
    path("api/products/<int:pk>/", views_management.api_product_detail),
    path("api/customers/", views_management.api_customers_list),
    path("api/customers/<int:pk>/", views_management.api_customer_detail),
    path("api/fdms/dashboard/", views_api.api_fdms_dashboard, name="api_fdms_dashboard"),
    path("api/dashboard/metrics/", views_dashboard.api_dashboard_metrics, name="api_dashboard_metrics"),
    path("api/dashboard/summary/", views_dashboard.api_dashboard_summary, name="api_dashboard_summary"),
    path("api/dashboard/receipts/", views_dashboard.api_dashboard_receipts, name="api_dashboard_receipts"),
    path("api/dashboard/errors/", views_dashboard.api_dashboard_errors, name="api_dashboard_errors"),
    path("api/dashboard/quickbooks/", views_dashboard.api_dashboard_quickbooks, name="api_dashboard_quickbooks"),
    path("api/dashboard/export/pdf/", views_dashboard.api_dashboard_export_pdf, name="api_dashboard_export_pdf"),
    path("api/dashboard/export/excel/", views_dashboard.api_dashboard_export_excel, name="api_dashboard_export_excel"),
    path("api/fdms/receipts/", views_api.api_fdms_receipts, name="api_fdms_receipts"),
    path("api/fdms/fiscal/", views_api.api_fdms_fiscal, name="api_fdms_fiscal"),
    path("api/integrations/quickbooks/validate-update/", views_api.api_qb_validate_invoice_update, name="api_qb_validate_invoice_update"),
    path("api/integrations/quickbooks/webhook/", views_api.api_qb_webhook, name="api_qb_webhook"),
    path("api/qb/webhook/", views_api.api_qb_webhook_verified, name="api_qb_webhook_verified"),
    path("api/integrations/quickbooks/invoice/", views_api.api_qb_fiscalise_invoice, name="api_qb_fiscalise_invoice"),
    path("api/integrations/quickbooks/oauth/connect/", views_api.api_qb_oauth_connect, name="api_qb_oauth_connect"),
    path("api/integrations/quickbooks/oauth/callback/", views_api.api_qb_oauth_callback, name="api_qb_oauth_callback"),
    path("api/integrations/quickbooks/sync/", views_api.api_qb_sync, name="api_qb_sync"),
    path("api/integrations/quickbooks/invoices/", views_api.api_qb_invoices, name="api_qb_invoices"),
    path("api/integrations/quickbooks/retry/", views_api.api_qb_retry_fiscalise, name="api_qb_retry_fiscalise"),
    path("logs/", views.fdms_logs, name="fdms_logs"),
    path("receipts/", views.receipt_history, name="receipt_history"),
    path("fiscal-day-dashboard/", lambda r: redirect("fdms_fiscal")),
    # FDMS Tailwind UI (Phase 11)
    path("fdms/", lambda r: redirect("fdms_dashboard")),
    path("fdms/dashboard/", views_fdms.fdms_dashboard, name="fdms_dashboard"),
    path("fdms/set-device/", views_fdms.fdms_set_device, name="fdms_set_device"),
    path("fdms/re-sync/", views_fdms.fdms_re_sync, name="fdms_re_sync"),
    path("fdms/device/", views_fdms.fdms_device, name="fdms_device"),
    path("fdms/fiscal/", views_fdms.fdms_fiscal, name="fdms_fiscal"),
    path("fdms/fiscal/open/", views_fdms.fdms_open_day_post, name="fdms_open_day"),
    path("fdms/fiscal/close/", views_fdms.fdms_close_day_post, name="fdms_close_day"),
    path("fdms/receipts/", views_fdms.fdms_receipts, name="fdms_receipts"),
    path("fdms/receipts/new/", views_fdms.fdms_receipt_new, name="fdms_receipt_new"),
    path("fdms/products/", views_fdms.fdms_products, name="fdms_products"),
    path("fdms/products/add/", views_fdms.fdms_product_form, name="fdms_product_add"),
    path("fdms/products/<int:pk>/edit/", views_fdms.fdms_product_form, name="fdms_product_edit"),
    path("fdms/tax-mappings/", views_fdms.fdms_tax_mappings, name="fdms_tax_mappings"),
    path("fdms/tax-mappings/add/", views_fdms.fdms_tax_mapping_form, name="fdms_tax_mapping_add"),
    path("fdms/tax-mappings/<int:pk>/edit/", views_fdms.fdms_tax_mapping_form, name="fdms_tax_mapping_edit"),
    path("fdms/sequences/adjust/", views_fdms.fdms_sequence_adjustment, name="fdms_sequence_adjustment"),
    path("fdms/settings/", views_fdms.fdms_settings, name="fdms_settings"),
    path("fdms/settings/company-logo/", views_fdms.fdms_settings_company_logo, name="fdms_settings_company_logo"),
    path("fdms/settings/company-logo/remove/", views_fdms.fdms_settings_company_logo_remove, name="fdms_settings_company_logo_remove"),
    path("fdms/settings/quickbooks/disconnect/", views_fdms.fdms_settings_qb_disconnect, name="fdms_settings_qb_disconnect"),
    path("fdms/receipts/<int:pk>/", views_fdms.fdms_receipt_detail, name="fdms_receipt_detail"),
    path("fdms/receipts/<int:pk>/invoice/", views_fdms.fdms_receipt_invoice, name="fdms_receipt_invoice"),
    path("fdms/receipts/<int:pk>/invoice/debit-note/html-pdf/", views_fdms.fdms_receipt_debit_note_html_pdf, name="fdms_receipt_debit_note_html_pdf"),
    path("fdms/receipts/<int:pk>/invoice/html-pdf/", views_fdms.fdms_receipt_invoice_html_pdf, name="fdms_receipt_invoice_html_pdf"),
    path("fdms/receipts/<int:pk>/invoice/pdf/", views_fdms.fdms_receipt_invoice_pdf, name="fdms_receipt_invoice_pdf"),
    path("fdms/receipts/<int:pk>/invoice-a4/pdf/", views_fdms.fdms_receipt_invoice_a4_pdf, name="fdms_receipt_invoice_a4_pdf"),
    path("fdms/receipts/<int:pk>/fiscal-invoice-a4/pdf/", views_fdms.fdms_receipt_fiscal_invoice_a4_pdf, name="fdms_receipt_fiscal_invoice_a4_pdf"),
    path("fdms/logs/", views_fdms.fdms_logs_tailwind, name="fdms_logs_tailwind"),
    path("fdms/audit/", views_fdms.fdms_audit, name="fdms_audit"),
    path("fdms/quickbooks-invoices/", views_fdms.fdms_qb_invoices, name="fdms_qb_invoices"),
    # Credit Note (standalone form only)
    path("fdms/credit-note/", views_credit_debit_forms.credit_note_form_view, name="fdms_credit_note"),
    path("fdms/credit-note/form/", views_credit_debit_forms.credit_note_form_view, name="fdms_credit_note_form"),
    path("api/credit-note-form/invoices/", views_credit_debit_forms.api_credit_note_form_invoices, name="api_credit_note_form_invoices"),
    path("fdms/debit-note/form/", views_credit_debit_forms.debit_note_form_view, name="fdms_debit_note_form"),
    # Invoice Excel import (Invoice 01)
    path("fdms/invoice-import/", views_invoice_import.invoice_import_step1, name="fdms_invoice_import_step1"),
    path("fdms/invoice-import/preview/", views_invoice_import.invoice_import_preview, name="fdms_invoice_import_preview"),
    path("fdms/invoice-import/success/<int:pk>/", views_invoice_import.invoice_import_success, name="fdms_invoice_import_success"),
    # Invoice Review import: upload Excel -> populate New Invoice form only (no FDMS submit)
    path("fdms/invoice-import-review/", views_invoice_import.import_invoice_review, name="fdms_invoice_import_review"),
]
