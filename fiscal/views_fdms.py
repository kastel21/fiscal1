"""Views for FDMS Tailwind UI (Phase 11)."""

import json
from datetime import date

from django.contrib import messages
from django.db.models import Max
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods

from fiscal.forms import DeviceRegistrationForm, SequenceAdjustmentForm
from fiscal.models import FDMSApiLog, FiscalDay, FiscalDevice, Receipt
from fiscal.services.audit_integrity import run_full_audit
from fiscal.services.config_service import get_config_status, get_latest_configs
from fiscal.services.fiscal_day_totals import get_fiscal_day_totals
from fiscal.services.invoice_layout_service import build_invoice_context
from fiscal.services.invoice_number import adjust_document_sequence
from fiscal.services.device_api import DeviceApiService
from fiscal.services.device_registration import DeviceRegistrationService
from fiscal.services.receipt_service import re_sync_device_from_get_status
from fiscal.utils import safe_json_dumps

from .views import _fetch_status_for_dashboard, get_device_for_request


def _fdms_context(device):
    """Build context dict for fdms dashboard/fiscal templates."""
    device_obj = {
        "device_id": device.device_id if device else None,
        "registered": bool(device and device.is_registered),
        "status": "Registered" if device and device.is_registered else "Not Registered",
        "cert_expiry": device.certificate_valid_till.strftime("%Y-%m-%d") if device and device.certificate_valid_till else None,
        "taxpayer_name": device.taxpayer_name if device else None,
        "taxpayer_tin": device.taxpayer_tin if device else None,
        "vat_number": device.vat_number if device else None,
        "is_vat_registered": bool(device and device.is_vat_registered),
    }
    fiscal_obj = {
        "day_no": None,
        "status": None,
        "date": None,
        "receipt_count": 0,
        "opened_at": None,
        "closed_at": None,
        "closing_error_code": None,
        "last_receipt_global_no": None,
        "current_fiscal_day": None,
        "recent_fiscal_days": [],
    }
    last_receipt_obj = None

    if device and device.is_registered:
        day_no = device.last_fiscal_day_no or 0
        fiscal_obj["day_no"] = device.last_fiscal_day_no
        fiscal_obj["status"] = device.fiscal_day_status or "—"
        fiscal_obj["date"] = date.today().isoformat()
        receipts_this_day = Receipt.objects.filter(device=device, fiscal_day_no=day_no)
        fiscal_obj["receipt_count"] = receipts_this_day.count()
        last_global = receipts_this_day.aggregate(m=Max("receipt_global_no"))["m"]
        fiscal_obj["last_receipt_global_no"] = last_global

        current_fd = FiscalDay.objects.filter(device=device, fiscal_day_no=day_no).first()
        if current_fd:
            fiscal_obj["current_fiscal_day"] = current_fd
            fiscal_obj["opened_at"] = current_fd.opened_at
            fiscal_obj["closed_at"] = getattr(current_fd, "closed_at", None)
            fiscal_obj["closing_error_code"] = getattr(current_fd, "closing_error_code", None) or ""

        fiscal_obj["recent_fiscal_days"] = list(
            FiscalDay.objects.filter(device=device).order_by("-fiscal_day_no")[:5]
        )

        last_rec = Receipt.objects.filter(device=device).order_by("-created_at").first()
        if last_rec:
            last_receipt_obj = {
                "global_no": last_rec.receipt_global_no,
                "total": str(last_rec.receipt_total) if last_rec.receipt_total else "—",
                "server_verified": bool(last_rec.receipt_server_signature),
            }

    config_status = get_config_status(device.device_id if device else None)
    configs = get_latest_configs(device.device_id if device else None)
    config_json = safe_json_dumps(configs.raw_response) if configs and configs.raw_response else ""
    return {
        "device": device_obj,
        "fiscal": fiscal_obj,
        "last_receipt": last_receipt_obj,
        "config_status": config_status["status"],
        "config_last_sync": config_status["lastSync"],
        "can_submit_receipt": config_status["status"] == "OK",
        "getconfig_response": config_json,
    }


@login_required
@login_required
@require_http_methods(["POST"])
def fdms_set_device(request):
    """POST: Set selected device for system-wide use. Redirects to ?next= or dashboard."""
    from .views import SESSION_DEVICE_KEY
    device_id = request.POST.get("device_id")
    if device_id:
        try:
            device_id = int(device_id)
            request.session[SESSION_DEVICE_KEY] = device_id
        except (TypeError, ValueError):
            pass
    next_url = request.GET.get("next") or request.POST.get("next") or "fdms_dashboard"
    return redirect(next_url)


def fdms_re_sync(request):
    """POST: Re-sync GetStatus + GetConfig, redirect back to dashboard."""
    if request.method != "POST":
        return redirect("fdms_dashboard")
    device = get_device_for_request(request)
    if not device:
        return redirect("fdms_dashboard")
    from fiscal.services.device_api import DeviceApiService
    re_sync_device_from_get_status(device)
    DeviceApiService().get_config(device)
    return redirect("fdms_dashboard")


@login_required
def fdms_dashboard(request):
    """FDMS dashboard - Tailwind UI. Any logged-in user can access."""
    device = get_device_for_request(request)
    ctx = _fdms_context(device)
    ctx["device"] = ctx["device"] if device else None  # Pass None so "No registered device" shows
    ctx["device_obj"] = device  # Full device for taxpayer/VAT in templates
    status_json, err = _fetch_status_for_dashboard(device) if device else (None, None)
    ctx["status_error"] = err
    ctx["getstatus_response"] = safe_json_dumps(status_json, indent=2) if status_json else ""
    if status_json and device:
        day_no = status_json.get("lastFiscalDayNo") or device.last_fiscal_day_no
        ctx["fiscal"]["status"] = status_json.get("fiscalDayStatus")
        ctx["fiscal"]["day_no"] = day_no
        ctx["fiscal"]["receipt_count"] = Receipt.objects.filter(
            device=device, fiscal_day_no=day_no or 0
        ).count()
    return render(request, "fdms/dashboard.html", ctx)


@login_required
@require_http_methods(["POST"])
def api_verify_taxpayer(request):
    """POST /api/verify-taxpayer/ - Verify taxpayer info before device registration."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    device_id = body.get("device_id")
    activation_key = (body.get("activation_key") or "").strip()
    device_serial_no = (body.get("device_serial_no") or "").strip()
    if not device_id or not activation_key or not device_serial_no:
        return JsonResponse(
            {"error": "device_id, activation_key, and device_serial_no are required"},
            status=400,
        )
    try:
        device_id = int(device_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "device_id must be an integer"}, status=400)
    if len(activation_key) != 8:
        return JsonResponse({"error": "activation_key must be exactly 8 characters"}, status=400)

    service = DeviceRegistrationService()
    data, err = service.verify_taxpayer_information(
        device_id=device_id,
        activation_key=activation_key,
        device_serial_no=device_serial_no,
    )
    if err:
        return JsonResponse({"error": err}, status=400)
    return JsonResponse({"success": True, "taxpayer": data})


@login_required
def fdms_device(request):
    """Device registration - any logged-in user with a tenant can add and register devices."""
    tenant = getattr(request, "tenant", None)
    if not tenant:
        return redirect("select_tenant")

    form = DeviceRegistrationForm()
    success_message = error_message = device_status = None

    if request.method == "POST":
        form = DeviceRegistrationForm(request.POST)
        if form.is_valid():
            service = DeviceRegistrationService()
            dev, err = service.register_device(
                tenant=tenant,
                device_id=form.cleaned_data["device_id"],
                activation_key=form.cleaned_data["activation_key"],
                device_serial_no=form.cleaned_data["device_serial_no"].strip(),
                device_model_name=form.cleaned_data["device_model_name"].strip(),
                device_model_version=form.cleaned_data["device_model_version"].strip(),
            )
            if err:
                error_message = err
            else:
                success_message = f"Device {dev.device_id} registered successfully."
                device_status = f"Device {dev.device_id} is registered. Certificate stored: Yes."
        else:
            error_message = "Please correct the errors below."

    return render(
        request,
        "fdms/device.html",
        {"form": form, "success_message": success_message, "error_message": error_message, "device_status": device_status},
    )


@login_required
def fdms_fiscal(request):
    """Fiscal day page - Tailwind UI. Device from GET or session. Tenant-scoped when request.tenant is set."""
    device = get_device_for_request(request)
    tenant = getattr(request, "tenant", None)
    devices_qs = FiscalDevice.objects.filter(is_registered=True)
    if tenant is not None:
        devices_qs = devices_qs.filter(tenant=tenant)
    devices = devices_qs.order_by("device_id")
    ctx = _fdms_context(device)
    ctx["device"] = {"device_id": device.device_id} if device else None
    ctx["device_obj"] = device
    ctx["devices"] = devices
    ctx["selected_device_id"] = device.device_id if device else None
    ctx["last_close_payload"] = ""
    ctx["open_msg"] = request.session.pop("fdms_open_msg", None)
    ctx["close_msg"] = request.session.pop("fdms_close_msg", None)

    if device and device.is_registered:
        status_json, _ = _fetch_status_for_dashboard(device)
        if status_json:
            ctx["fiscal"]["status"] = status_json.get("fiscalDayStatus")
            ctx["fiscal"]["day_no"] = status_json.get("lastFiscalDayNo")
        close_log_qs = FDMSApiLog.objects.filter(endpoint__endswith="/CloseDay").order_by("-created_at")
        if tenant is not None:
            close_log_qs = close_log_qs.filter(tenant=tenant)
        last_close = close_log_qs.first()
        if last_close and last_close.request_payload:
            ctx["last_close_payload"] = safe_json_dumps(last_close.request_payload)
        day_no = ctx["fiscal"].get("day_no") or device.last_fiscal_day_no
        ctx["fiscal_day_totals"] = get_fiscal_day_totals(device, day_no)
    else:
        ctx["fiscal_day_totals"] = get_fiscal_day_totals(None, None)
    return render(request, "fdms/fiscal_day.html", ctx)


@login_required
def fdms_open_day_post(request):
    """POST: Open fiscal day, redirect back with message."""
    if request.method != "POST":
        return redirect("fdms_fiscal")
    device = get_device_for_request(request)
    if not device:
        request.session["fdms_open_msg"] = "No registered device."
        return redirect("fdms_fiscal")
    service = DeviceApiService()
    _, err = service.open_day(device)
    request.session["fdms_open_msg"] = err or "Fiscal day opened."
    return redirect("fdms_fiscal")


@login_required
def fdms_close_day_post(request):
    """POST: Close fiscal day, redirect back with message."""
    if request.method != "POST":
        return redirect("fdms_fiscal")
    device = get_device_for_request(request)
    if not device:
        request.session["fdms_close_msg"] = "No registered device."
        return redirect("fdms_fiscal")
    service = DeviceApiService()
    data, err = service.close_day(device)
    if err:
        request.session["fdms_close_msg"] = err
    else:
        request.session["fdms_close_msg"] = f"CloseDay initiated. Poll status until closed. operationID: {data.get('operationID', 'N/A')}"
    return redirect("fdms_fiscal")


@login_required
def fdms_receipts(request):
    """Receipts list - Tailwind UI. Optional ?status=, ?doc_type=, ?device_id=. Tenant-scoped when request.tenant is set."""
    tenant = getattr(request, "tenant", None)
    device_id = request.GET.get("device_id", "").strip()
    status = request.GET.get("status", "").strip().lower()
    doc_type = request.GET.get("doc_type", "").strip().lower()
    queryset = Receipt.objects.all()
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    queryset = queryset.select_related("device").order_by("-created_at")
    current = get_device_for_request(request)
    if device_id and device_id.isdigit():
        queryset = queryset.filter(device__device_id=int(device_id))
    if status == "draft":
        from django.db.models import Q
        queryset = queryset.filter(Q(fdms_receipt_id__isnull=True) | Q(fdms_receipt_id=0))
    elif status == "fiscalised":
        queryset = queryset.filter(fdms_receipt_id__isnull=False).exclude(fdms_receipt_id=0)
    if doc_type == "credit_note":
        queryset = queryset.filter(document_type="CREDIT_NOTE")
    elif doc_type == "debit_note":
        queryset = queryset.filter(document_type="DEBIT_NOTE")
    elif doc_type == "invoice":
        queryset = queryset.filter(document_type="INVOICE")
    receipts = list(queryset[:200])
    devices_qs = FiscalDevice.objects.filter(is_registered=True)
    if tenant is not None:
        devices_qs = devices_qs.filter(tenant=tenant)
    devices = devices_qs.order_by("device_id")
    selected = int(device_id) if device_id and device_id.isdigit() else None
    return render(
        request,
        "fdms/receipts_list.html",
        {"receipts": receipts, "devices": devices, "filters": {"device_id": device_id, "selected_device_id": selected, "status": status, "doc_type": doc_type}},
    )


@login_required
def fdms_receipt_invoice(request, pk):
    """Tax Invoice, Credit Note or Debit Note layout for print. PDF download uses the exact same template and context."""
    from fiscal.services.fiscal_invoice_context import get_receipt_print_template_and_context

    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = get_object_or_404(qs, pk=pk)
    template_name, ctx = get_receipt_print_template_and_context(receipt)
    return render(request, template_name, ctx)


@login_required
def fdms_receipt_invoice_pdf(request, pk):
    """Tax Invoice PDF using current template (invoices/fiscal_invoice_a4.html). Always generated on download. Tenant-scoped when request.tenant is set."""
    from django.http import HttpResponse, HttpResponseServerError
    from django.core.exceptions import ValidationError
    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = get_object_or_404(qs, pk=pk)
    try:
        from fiscal.services.pdf_generator import generate_fiscal_invoice_pdf_from_template
        pdf_bytes = generate_fiscal_invoice_pdf_from_template(receipt, request=request)
    except ValidationError as e:
        return HttpResponseServerError(
            f"PDF generation failed: {e}. Ensure WeasyPrint is installed (pip install weasyprint).",
            content_type="text/plain",
        )
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    doc_type = "Credit-Note" if receipt.receipt_type == "CreditNote" else "Debit-Note" if receipt.receipt_type == "DebitNote" else "Invoice"
    resp["Content-Disposition"] = f'attachment; filename="FDMS-{doc_type}-{receipt.fdms_receipt_id or receipt.receipt_global_no}.pdf"'
    return resp


@login_required
def fdms_receipt_invoice_html_pdf(request, pk):
    """
    Download PDF generated from the exact same rendered HTML template/context as the print view.
    This endpoint intentionally bypasses legacy PDF helper functions.
    """
    from django.http import HttpResponse, HttpResponseServerError
    from django.core.exceptions import ValidationError
    from django.template.loader import render_to_string
    from fiscal.services.fiscal_invoice_context import get_receipt_print_template_and_context
    from fiscal.services.pdf_generator import _html_to_pdf

    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = get_object_or_404(qs, pk=pk)

    try:
        template_name, ctx = get_receipt_print_template_and_context(receipt)
        html = render_to_string(template_name, ctx)
        pdf_bytes = _html_to_pdf(html, request=request)
    except ValidationError as e:
        return HttpResponseServerError(
            f"PDF generation failed: {e}. Ensure WeasyPrint or xhtml2pdf is installed.",
            content_type="text/plain",
        )
    except Exception as e:
        return HttpResponseServerError(f"PDF generation failed: {e}", content_type="text/plain")

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    doc_type = "Credit-Note" if receipt.receipt_type == "CreditNote" else "Debit-Note" if receipt.receipt_type == "DebitNote" else "Invoice"
    resp["Content-Disposition"] = f'attachment; filename="FDMS-HTML-{doc_type}-{receipt.fdms_receipt_id or receipt.receipt_global_no}.pdf"'
    return resp


@login_required
def fdms_receipt_debit_note_html_pdf(request, pk):
    """
    Download Debit Note PDF from the exact rendered debit-note HTML view/template.
    """
    from django.http import HttpResponse, HttpResponseServerError, HttpResponseBadRequest
    from django.core.exceptions import ValidationError
    from django.template.loader import render_to_string
    from fiscal.services.fiscal_invoice_context import get_receipt_print_template_and_context
    from fiscal.services.pdf_generator import _html_to_pdf

    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = get_object_or_404(qs, pk=pk)

    if receipt.receipt_type != "DebitNote":
        return HttpResponseBadRequest("This endpoint is only for Debit Note PDFs.", content_type="text/plain")

    try:
        template_name, ctx = get_receipt_print_template_and_context(receipt)
        html = render_to_string(template_name, ctx)
        pdf_bytes = _html_to_pdf(html, request=request)
    except ValidationError as e:
        return HttpResponseServerError(
            f"PDF generation failed: {e}. Ensure WeasyPrint or xhtml2pdf is installed.",
            content_type="text/plain",
        )
    except Exception as e:
        return HttpResponseServerError(f"PDF generation failed: {e}", content_type="text/plain")

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = (
        f'attachment; filename="FDMS-HTML-Debit-Note-{receipt.fdms_receipt_id or receipt.receipt_global_no}.pdf"'
    )
    return resp


@login_required
def fdms_receipt_invoice_a4_pdf(request, pk):
    """
    Download Tax Invoice A4 PDF (same template as main download). Always generated from current template.
    Tenant-scoped when request.tenant is set.
    """
    from django.http import HttpResponse, HttpResponseServerError
    from django.core.exceptions import ValidationError
    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = get_object_or_404(qs, pk=pk)
    try:
        from fiscal.services.pdf_generator import generate_fiscal_invoice_pdf_from_template
        pdf_bytes = generate_fiscal_invoice_pdf_from_template(receipt, request=request)
    except ValidationError as e:
        return HttpResponseServerError(
            f"PDF generation failed: {e}. Ensure WeasyPrint is installed (pip install weasyprint).",
            content_type="text/plain",
        )
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="InvoiceA4-{receipt.fdms_receipt_id or receipt.receipt_global_no}.pdf"'
    return resp


@login_required
def fdms_receipt_fiscal_invoice_a4_pdf(request, pk):
    """
    Section 10 compliant A4 Tax Invoice PDF (invoices/fiscal_invoice_a4.html).
    Validates fiscal_signature, receipt_global_no, fiscal_invoice_number, totals before generating.
    Does NOT generate PDF if validation fails (returns 400).
    """
    from django.http import HttpResponse, HttpResponseBadRequest
    from django.core.exceptions import ValidationError
    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = get_object_or_404(qs, pk=pk)
    try:
        from fiscal.services.pdf_generator import generate_fiscal_invoice_a4_pdf_section10
        pdf_bytes = generate_fiscal_invoice_a4_pdf_section10(receipt, request=request)
    except ValidationError as e:
        return HttpResponseBadRequest(f"Validation error: {e}", content_type="text/plain")
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    fn = getattr(receipt, "fiscal_invoice_number", None) or receipt.invoice_no or receipt.receipt_global_no
    resp["Content-Disposition"] = f'attachment; filename="Fiscal-Invoice-A4-{fn}.pdf"'
    return resp


@login_required
def fdms_receipt_detail(request, pk):
    """Receipt detail - Tailwind UI. Tenant-scoped when request.tenant is set."""
    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = get_object_or_404(qs, pk=pk)
    submit_debug = None
    session_debug = request.session.pop("last_submit_debug", None)
    if session_debug and session_debug.get("receipt_id") == receipt.pk:
        submit_debug = {
            "request": session_debug.get("request", ""),
            "response_status": session_debug.get("response_status"),
            "response": session_debug.get("response", ""),
        }
    qr_image_base64 = ""
    if receipt.qr_code_value:
        from fiscal.services.qr_generator import generate_qr_base64
        qr_image_base64 = generate_qr_base64(receipt.qr_code_value)
    from fiscal.services.receipt_submission_response_service import get_validation_errors_for_receipt
    validation_errors = get_validation_errors_for_receipt(receipt)
    return render(
        request,
        "fdms/receipt_detail.html",
        {
            "receipt": receipt,
            "submit_debug": submit_debug,
            "qr_image_base64": qr_image_base64,
            "validation_errors": validation_errors,
        },
    )


@login_required
def fdms_receipt_new(request):
    """Create invoice / new receipt form - full form with customer, items, payments. Submits via /api/invoices/."""
    device = get_device_for_request(request)
    config_status = get_config_status(device.device_id if device else None)
    return render(
        request,
        "fdms/receipt_new.html",
        {
            "config_status": config_status["status"],
            "config_last_sync": config_status["lastSync"],
            "can_submit_receipt": config_status["status"] == "OK",
        },
    )


@login_required
def fdms_logs_tailwind(request):
    """FDMS logs - Tailwind UI. Tenant-scoped when request.tenant is set."""
    from datetime import datetime
    tenant = getattr(request, "tenant", None)
    queryset = FDMSApiLog.objects.order_by("-created_at")
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    endpoint = request.GET.get("endpoint", "").strip()
    if endpoint:
        queryset = queryset.filter(endpoint__icontains=endpoint)
    operation_id = request.GET.get("operation_id", "").strip()
    if operation_id:
        queryset = queryset.filter(operation_id__icontains=operation_id)
    status_code = request.GET.get("status_code", "").strip()
    if status_code and status_code.isdigit():
        queryset = queryset.filter(status_code=int(status_code))
    date_from = request.GET.get("date_from", "").strip()
    if date_from:
        try:
            queryset = queryset.filter(created_at__date__gte=datetime.strptime(date_from, "%Y-%m-%d").date())
        except ValueError:
            pass
    date_to = request.GET.get("date_to", "").strip()
    if date_to:
        try:
            queryset = queryset.filter(created_at__date__lte=datetime.strptime(date_to, "%Y-%m-%d").date())
        except ValueError:
            pass
    logs = list(queryset[:100])
    for log in logs:
        log.request_json = safe_json_dumps(log.request_payload) if log.request_payload else ""
        log.response_json = safe_json_dumps(log.response_payload) if log.response_payload else ""
    return render(
        request,
        "fdms/logs.html",
        {
            "logs": logs,
            "filters": {"endpoint": endpoint, "operation_id": operation_id, "status_code": status_code, "date_from": date_from, "date_to": date_to},
        },
    )


@login_required
def fdms_audit(request):
    """Integrity audit page - Tailwind UI."""
    result = None
    if request.method == "POST":
        result = run_full_audit()
    return render(request, "fdms/audit.html", {"result": result})


@login_required
def fdms_products(request):
    """Products list - admin only."""
    if not request.user.is_staff:
        return redirect("fdms_dashboard")
    return render(request, "fdms/products_list.html", {})


@login_required
def fdms_product_form(request, pk=None):
    """Add or edit product - admin only."""
    if not request.user.is_staff:
        return redirect("fdms_dashboard")
    return render(request, "fdms/product_form.html", {"product_id": pk or ""})


@login_required
def fdms_tax_mappings(request):
    """Tax Mappings list - map local tax codes to FDMS taxID."""
    if not request.user.is_staff:
        return redirect("fdms_dashboard")
    return render(request, "fdms/tax_mappings_list.html", {})


@login_required
def fdms_tax_mapping_form(request, pk=None):
    """Add or edit tax mapping."""
    if not request.user.is_staff:
        return redirect("fdms_dashboard")
    return render(request, "fdms/tax_mapping_form.html", {"mapping_id": pk or ""})


@login_required
@require_http_methods(["GET", "POST"])
def fdms_sequence_adjustment(request):
    """Admin-only sequence adjustment form for manual number resync/skip."""
    if not request.user.is_staff:
        return redirect("fdms_dashboard")

    result = None
    form = SequenceAdjustmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        document_type = form.cleaned_data["document_type"]
        year = form.cleaned_data["year"]
        mode = form.cleaned_data["mode"]
        value = form.cleaned_data["value"]
        reason = form.cleaned_data["reason"]
        kwargs = {"set_next": value} if mode == "set_next" else {"skip_by": value}
        try:
            result = adjust_document_sequence(
                document_type=document_type,
                year=year,
                reason=reason,
                user=request.user,
                **kwargs,
            )
            messages.success(
                request,
                f"Sequence updated. Next number: {result['next_number_preview']}",
            )
            form = SequenceAdjustmentForm(initial={
                "document_type": document_type,
                "year": year,
                "mode": mode,
                "value": value,
            })
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "fdms/sequence_adjustment.html",
        {
            "form": form,
            "result": result,
        },
    )


@login_required
def fdms_settings(request):
    """Settings page - QuickBooks, company logo, and other integrations. Tenant-scoped QB connection."""
    from django.conf import settings as django_settings
    from fiscal.models import Company, QuickBooksConnection

    tenant = getattr(request, "tenant", None)
    qb_connection = (
        QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()
        if tenant else None
    )
    qb_credentials_configured = bool(getattr(django_settings, "QB_CLIENT_ID", "") or "")
    company = Company.objects.filter(tenant=tenant).first() if tenant else Company.objects.first()
    return render(
        request,
        "fdms/settings.html",
        {
            "qb_connection": qb_connection,
            "qb_connected": qb_connection is not None,
            "qb_credentials_configured": qb_credentials_configured,
            "company": company,
        },
    )


@login_required
@require_http_methods(["POST"])
def fdms_settings_company_logo(request):
    """Upload company logo (appears on tax invoices). Creates company if none exists."""
    from django.contrib import messages
    from django.shortcuts import redirect
    from fiscal.models import Company

    company = Company.objects.first()
    if not company:
        company = Company(
            name="",
            tin="",
            address="",
            phone="",
            email="",
        )
        company.save()
    logo_file = request.FILES.get("logo")
    if not logo_file:
        messages.warning(request, "No file selected. Please choose an image to upload.")
        return redirect("fdms_settings")
    if not logo_file.content_type or not logo_file.content_type.startswith("image/"):
        messages.warning(request, "Please upload an image file (e.g. PNG, JPEG).")
        return redirect("fdms_settings")
    company.logo = logo_file
    company.save(update_fields=["logo"])
    messages.success(request, "Company logo updated. It will appear on tax invoices.")
    return redirect("fdms_settings")


@login_required
@require_http_methods(["POST"])
def fdms_settings_company_logo_remove(request):
    """Remove company logo."""
    from django.contrib import messages
    from django.shortcuts import redirect
    from fiscal.models import Company

    company = Company.objects.first()
    if company and company.logo:
        company.logo.delete(save=False)
        company.logo = None
        company.save(update_fields=["logo"])
        messages.success(request, "Company logo removed.")
    return redirect("fdms_settings")


@login_required
@require_http_methods(["POST"])
def fdms_settings_qb_disconnect(request):
    """Disconnect QuickBooks for current tenant (set is_active=False)."""
    from fiscal.models import QuickBooksConnection

    tenant = getattr(request, "tenant", None)
    conn = (
        QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()
        if tenant else None
    )
    if conn:
        conn.is_active = False
        conn.save(update_fields=["is_active"])
        from django.contrib import messages
        messages.success(request, "QuickBooks disconnected.")
    return redirect("fdms_settings")


@login_required
def fdms_qb_invoices(request):
    """QuickBooks invoices - fiscal status, retry button. Tenant-scoped."""
    from fiscal.models import QuickBooksInvoice

    tenant = getattr(request, "tenant", None)
    qs = QuickBooksInvoice.objects.select_related("fiscal_receipt").order_by("-created_at")
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    invoices = list(qs[:100])
    return render(request, "fdms/qb_invoices.html", {"invoices": invoices})
