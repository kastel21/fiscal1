"""
QuickBooks OAuth2 and API URL configuration.
"""

from django.urls import path

from . import views

app_name = "quickbooks"

urlpatterns = [
    path("connect/", views.qb_connect, name="qb_connect"),
    path("callback/", views.qb_callback, name="qb_callback"),
    path("disconnect/", views.qb_disconnect, name="qb_disconnect"),
    path("webhook/", views.qb_webhook, name="qb_webhook"),
    path("invoices/pull/", views.qb_invoices_pull, name="qb_invoices_pull"),
    path("invoices/push/<str:invoice_id>/", views.qb_invoices_push, name="qb_invoices_push"),
]
