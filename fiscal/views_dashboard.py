"""Dashboard API views. Read-only, FDMS-confirmed data only."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse

from dashboard.services.metrics_service import get_metrics
from fiscal.services.dashboard_service import (
    get_errors,
    get_quickbooks_stub,
    get_receipts,
    get_summary,
)


def _get_user_role(request):
    """Resolve role from user groups: cashier, accountant, admin. Groups take precedence over is_staff."""
    if request.user.groups.filter(name="cashier").exists():
        return "cashier"
    if request.user.groups.filter(name="accountant").exists():
        return "accountant"
    if request.user.is_superuser or request.user.is_staff:
        return "admin"
    return "admin"  # default for staff-only views


def _apply_role_filter(data: dict, role: str) -> dict:
    """Filter dashboard summary by role per FDMS_Dashboard_Metrics spec."""
    if role == "admin":
        return data
    if role == "accountant":
        # Hide status.certificate days detail if too sensitive; accountant sees financials
        return data
    if role == "cashier":
        # Cashier: today's invoices, pending receipts only; no certs or counters
        out = dict(data)
        if "status" in out:
            out["status"] = {k: "***" if k in ("certificate", "lastSync") else v for k, v in out["status"].items()}
        if "compliance" in out:
            out["compliance"] = {k: "***" if k in ("lastReceiptGlobalNo",) else v for k, v in out["compliance"].items()}
        return out
    return data


@login_required
def api_dashboard_metrics(request):
    """GET /api/dashboard/metrics/ - KPI metrics for real-time dashboard."""
    device_id = request.GET.get("device_id")
    if device_id and str(device_id).isdigit():
        device_id = int(device_id)
    else:
        device_id = None
    data = get_metrics(device_id)
    return JsonResponse(data)


@login_required
def api_dashboard_summary(request):
    """GET /api/dashboard/summary?range=today|week|month"""
    range_key = request.GET.get("range", "today")
    if range_key not in ("today", "week", "month"):
        range_key = "today"
    device_id = request.GET.get("device_id")
    if device_id and str(device_id).isdigit():
        device_id = int(device_id)
    else:
        device_id = None
    tenant = getattr(request, "tenant", None)
    data = get_summary(device_id, range_key, tenant=tenant)
    role = _get_user_role(request)
    data = _apply_role_filter(data, role)
    return JsonResponse(data)


@login_required
def api_dashboard_receipts(request):
    """GET /api/dashboard/receipts?range=today|week|month&status=draft|fiscalised|failed"""
    range_key = request.GET.get("range", "today")
    if range_key not in ("today", "week", "month"):
        range_key = "today"
    status_filter = request.GET.get("status")  # optional
    if status_filter and status_filter not in ("draft", "fiscalised", "failed"):
        status_filter = None
    device_id = request.GET.get("device_id")
    if device_id and str(device_id).isdigit():
        device_id = int(device_id)
    else:
        device_id = None
    tenant = getattr(request, "tenant", None)
    receipts = get_receipts(device_id, range_key, status_filter, tenant=tenant)
    return JsonResponse({"receipts": receipts})


@login_required
def api_dashboard_errors(request):
    """GET /api/dashboard/errors?range=today|week|month"""
    range_key = request.GET.get("range", "today")
    if range_key not in ("today", "week", "month"):
        range_key = "today"
    device_id = request.GET.get("device_id")
    if device_id and str(device_id).isdigit():
        device_id = int(device_id)
    else:
        device_id = None
    tenant = getattr(request, "tenant", None)
    errors = get_errors(device_id, range_key, tenant=tenant)
    return JsonResponse({"errors": errors})


@login_required
def api_dashboard_quickbooks(request):
    """GET /api/dashboard/quickbooks - stub when no QB integration."""
    tenant = getattr(request, "tenant", None)
    data = get_quickbooks_stub(tenant=tenant)
    return JsonResponse(data)


@login_required
def api_dashboard_export_pdf(request):
    """GET /api/dashboard/export/pdf?range=today|week|month"""
    range_key = request.GET.get("range", "month")
    if range_key not in ("today", "week", "month"):
        range_key = "month"
    tenant = getattr(request, "tenant", None)
    data = get_summary(None, range_key, tenant=tenant)
    from .export_utils import render_pdf
    pdf_bytes = render_pdf(data, range_key)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="fdms-dashboard-%s.pdf"' % range_key
    return resp


@login_required
def api_dashboard_export_excel(request):
    """GET /api/dashboard/export/excel?range=today|week|month. Tenant-scoped when request.tenant is set."""
    range_key = request.GET.get("range", "month")
    if range_key not in ("today", "week", "month"):
        range_key = "month"
    tenant = getattr(request, "tenant", None)
    from .export_utils import render_excel
    xlsx_bytes = render_excel(range_key, tenant=tenant)
    resp = HttpResponse(xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = 'attachment; filename="fdms-dashboard-%s.xlsx"' % range_key
    return resp
