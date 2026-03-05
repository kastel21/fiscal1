"""Views for fiscal app."""

import json
import logging

from django.conf import settings

logger = logging.getLogger("fiscal")
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from fiscal.forms import DeviceRegistrationForm
from fiscal.models import FDMSApiLog, FiscalDay, FiscalDevice, Receipt
from fiscal.utils import redact_for_ui, safe_json_dumps
from fiscal.services.device_api import DeviceApiService
from fiscal.services.device_registration import DeviceRegistrationService
from fiscal.services.fdms_events import emit_metrics_updated
from fiscal.services.receipt_service import re_sync_device_from_get_status, submit_receipt
from fiscal import tasks as fiscal_tasks


SESSION_DEVICE_KEY = "fdms_selected_device_id"


def _get_device(device_id=None):
    """Return first registered device or device by ID. Only for tenant-exempt paths (e.g. admin)."""
    if device_id is not None:
        try:
            return FiscalDevice.objects.get(device_id=device_id, is_registered=True)
        except (FiscalDevice.DoesNotExist, TypeError, ValueError):
            return None
    return FiscalDevice.objects.filter(is_registered=True).first()


def get_device_for_request(request):
    """
    Return the device for this request. When request.tenant exists, always resolve by tenant only.
    Never fall back to global device when tenant is set. Device selection (GET/POST/session) is
    scoped to the tenant's devices.
    """
    tenant = getattr(request, "tenant", None)
    device_id = request.GET.get("device_id") or request.POST.get("device_id") or request.session.get(SESSION_DEVICE_KEY)
    if device_id is not None:
        try:
            device_id = int(device_id)
        except (TypeError, ValueError):
            device_id = None

    if tenant is not None:
        # Tenant-scoped: only devices belonging to this tenant.
        qs = FiscalDevice.objects.filter(tenant=tenant, is_registered=True)
        if device_id is not None:
            device = qs.filter(device_id=device_id).first()
        else:
            device = qs.order_by("device_id").first()
        if request.GET.get("device_id") or request.POST.get("device_id"):
            if device is not None and device_id is not None:
                request.session[SESSION_DEVICE_KEY] = device_id
            elif SESSION_DEVICE_KEY in request.session:
                del request.session[SESSION_DEVICE_KEY]
        return device

    # Tenant-exempt path (e.g. /admin/): legacy behavior.
    if request.GET.get("device_id") or request.POST.get("device_id"):
        if device_id is not None:
            request.session[SESSION_DEVICE_KEY] = device_id
        elif SESSION_DEVICE_KEY in request.session:
            del request.session[SESSION_DEVICE_KEY]
    return _get_device(device_id)


def _fetch_status_for_dashboard(device):
    """Call get_status (which calls update_device_status). Return (status_json, error)."""
    from fiscal.services.fdms_device_service import FDMSDeviceService, FDMSDeviceError
    try:
        service = FDMSDeviceService()
        return service.get_status(device), None
    except FDMSDeviceError as e:
        return None, str(e)
    except Exception as e:
        err_lower = str(e).lower()
        return None, "FDMS Unreachable" if "connection" in err_lower or "timeout" in err_lower else str(e)


@staff_member_required
def dashboard(request):
    """Dashboard: device status, fiscal day info. Auto-refreshes. Device from GET or session. Tenant-scoped when request.tenant is set."""
    device = get_device_for_request(request)
    device_id = device.device_id if device else None

    tenant = getattr(request, "tenant", None)
    log_qs = FDMSApiLog.objects.order_by("-created_at")
    if tenant is not None:
        log_qs = log_qs.filter(tenant=tenant)
    last_log = log_qs.first()
    last_log_request = safe_json_dumps(last_log.request_payload) if last_log and last_log.request_payload else ""
    last_log_response = safe_json_dumps(last_log.response_payload) if last_log and last_log.response_payload else ""

    close_qs = FDMSApiLog.objects.filter(endpoint__endswith="/CloseDay").order_by("-created_at")
    if tenant is not None:
        close_qs = close_qs.filter(tenant=tenant)
    last_close_log = close_qs.first()
    last_close_request = safe_json_dumps(last_close_log.request_payload) if last_close_log and last_close_log.request_payload else ""
    last_close_response = safe_json_dumps(last_close_log.response_payload) if last_close_log and last_close_log.response_payload else ""

    context = {
        "device": device,
        "device_id": device_id,
        "device_registered": device.is_registered if device else False,
        "fiscal_status": None,
        "last_day_no": None,
        "last_receipt_no": None,
        "closing_error": None,
        "status_error": None,
        "last_log": last_log,
        "last_log_request": last_log_request,
        "last_log_response": last_log_response,
        "last_close_log": last_close_log,
        "last_close_request": last_close_request,
        "last_close_response": last_close_response,
    }

    if device and device.is_registered:
        status_json, err = _fetch_status_for_dashboard(device)
        if err:
            context["status_error"] = err
            context["fiscal_status"] = device.fiscal_day_status
            context["last_day_no"] = device.last_fiscal_day_no
            context["last_receipt_no"] = device.last_receipt_global_no
        elif status_json:
            context["fiscal_status"] = status_json.get("fiscalDayStatus")
            context["last_day_no"] = status_json.get("lastFiscalDayNo")
            context["last_receipt_no"] = status_json.get("lastReceiptGlobalNo")
            context["closing_error"] = status_json.get("fiscalDayClosingErrorCode")

    return render(request, "fiscal/fiscal_day_control.html", context)


@staff_member_required
def open_day_api(request):
    """POST: Open a new fiscal day. Returns JSON. Device from POST/GET/body or session."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    device_id = request.POST.get("device_id") or request.GET.get("device_id") or request.session.get(SESSION_DEVICE_KEY)
    if not device_id and request.content_type == "application/json":
        try:
            body = json.loads(request.body)
            device_id = body.get("device_id")
        except Exception:
            pass
    device = _get_device(device_id)
    if not device:
        return JsonResponse(
            {"success": False, "error": "No registered device"},
            status=404,
        )
    use_async = request.GET.get("async") == "1" or request.headers.get("X-Use-Celery") == "1"
    if use_async:
        task = fiscal_tasks.open_day_task.delay(device.device_id)
        return JsonResponse({
            "success": True,
            "status": "queued",
            "task_id": str(task.id),
        })
    service = DeviceApiService()
    fiscal_day, err = service.open_day(device)
    if err:
        return JsonResponse({"success": False, "error": err}, status=400)
    emit_metrics_updated()
    return JsonResponse(
        {
            "success": True,
            "fiscal_day_no": fiscal_day.fiscal_day_no,
            "fiscal_day_status": "FiscalDayOpened",
        }
    )


@staff_member_required
def close_day_api(request):
    """POST: Close fiscal day. Returns JSON. Device from POST/GET/body or session."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    device_id = request.POST.get("device_id") or request.GET.get("device_id") or request.session.get(SESSION_DEVICE_KEY)
    if not device_id and request.content_type == "application/json":
        try:
            body = json.loads(request.body)
            device_id = body.get("device_id")
        except Exception:
            pass
    device = _get_device(device_id)
    if not device:
        return JsonResponse(
            {"success": False, "error": "No registered device"},
            status=404,
        )
    use_async = request.GET.get("async") == "1" or request.headers.get("X-Use-Celery") == "1"
    if use_async:
        task = fiscal_tasks.close_day_task.delay(device.device_id)
        return JsonResponse({
            "success": True,
            "status": "queued",
            "task_id": str(task.id),
        })
    service = DeviceApiService()
    data, err = service.close_day(device)
    if err:
        return JsonResponse({"success": False, "error": err}, status=400)
    emit_metrics_updated()
    return JsonResponse(
        {
            "success": True,
            "fiscal_day_status": "FiscalDayCloseInitiated",
            "operation_id": data.get("operationID"),
        }
    )


@staff_member_required
def submit_receipt_api(request):
    """POST: Submit receipt to FDMS. Expects JSON body with receipt data."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        resp = {"success": False, "error": "Invalid JSON"}
        logger.debug("[submit_receipt_api] RESPONSE: %s", json.dumps(resp))
        return JsonResponse(resp, status=400)

    logger.debug("[submit_receipt_api] REQUEST payload: %s", safe_json_dumps(body))

    device_id = body.get("device_id")
    if device_id is not None:
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            device_id = None
    device = _get_device(device_id)
    if not device:
        resp = {"success": False, "error": "No registered device"}
        logger.debug("[submit_receipt_api] RESPONSE: %s", json.dumps(resp))
        return JsonResponse(resp, status=404)

    receipt_type = body.get("receipt_type", "FiscalInvoice")
    receipt_currency = body.get("receipt_currency", "USD")
    fiscal_day_no = body.get("fiscal_day_no") or device.last_fiscal_day_no
    if fiscal_day_no is None:
        resp = {"success": False, "error": "fiscal_day_no required"}
        logger.debug("[submit_receipt_api] RESPONSE: %s", json.dumps(resp))
        return JsonResponse(resp, status=400)

    original_invoice_no = body.get("original_invoice_no", "").strip() or ""
    original_receipt_global_no_raw = body.get("original_receipt_global_no")
    original_receipt_global_no = None
    if original_receipt_global_no_raw is not None:
        try:
            original_receipt_global_no = int(original_receipt_global_no_raw)
        except (ValueError, TypeError):
            pass
    # FiscalInvoice: always use server-generated invoice number to avoid duplicates
    invoice_no_submit = "" if receipt_type == "FiscalInvoice" else (body.get("invoice_no") or "")
    use_async = body.get("async") is True or request.GET.get("async") == "1" or request.headers.get("X-Use-Celery") == "1"
    if use_async:
        task = fiscal_tasks.submit_receipt_task.delay(
            device_id=device.device_id,
            fiscal_day_no=int(fiscal_day_no),
            receipt_type=receipt_type,
            receipt_currency=receipt_currency,
            invoice_no=invoice_no_submit,
            receipt_lines=body.get("receipt_lines", []),
            receipt_taxes=body.get("receipt_taxes", []),
            receipt_payments=body.get("receipt_payments", []),
            receipt_total=float(body.get("receipt_total", 0)),
            receipt_lines_tax_inclusive=body.get("receipt_lines_tax_inclusive", True),
            original_invoice_no=original_invoice_no if receipt_type == "CreditNote" else "",
            original_receipt_global_no=original_receipt_global_no if receipt_type == "CreditNote" else None,
        )
        resp = {"success": True, "status": "queued", "task_id": str(task.id)}
        logger.debug("[submit_receipt_api] RESPONSE (async): %s", json.dumps(resp, indent=2))
        return JsonResponse(resp)
    try:
        receipt_obj, err = submit_receipt(
            device=device,
            fiscal_day_no=int(fiscal_day_no),
            receipt_type=receipt_type,
            receipt_currency=receipt_currency,
            invoice_no=invoice_no_submit,
            receipt_lines=body.get("receipt_lines", []),
            receipt_taxes=body.get("receipt_taxes", []),
            receipt_payments=body.get("receipt_payments", []),
            receipt_total=float(body.get("receipt_total", 0)),
            receipt_lines_tax_inclusive=body.get("receipt_lines_tax_inclusive", True),
            original_invoice_no=original_invoice_no if receipt_type == "CreditNote" else "",
            original_receipt_global_no=original_receipt_global_no if receipt_type == "CreditNote" else None,
        )
    except Exception as e:
        logger.exception("submit_receipt_api: submit_receipt failed")
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    if err:
        resp = {"success": False, "error": redact_for_ui(err)}
        logger.debug("[submit_receipt_api] RESPONSE (error): %s", json.dumps(resp, indent=2))
        return JsonResponse(resp, status=400)
    emit_metrics_updated()
    resp = {
        "success": True,
        "receipt_id": receipt_obj.fdms_receipt_id,
        "receipt_global_no": receipt_obj.receipt_global_no,
        "receipt_counter": receipt_obj.receipt_counter,
    }
    logger.debug("[submit_receipt_api] RESPONSE (success): %s", json.dumps(resp, indent=2))
    return JsonResponse(resp)


@staff_member_required
def re_sync_api(request):
    """POST: Re-sync device state from FDMS GetStatus. Returns JSON. Device from POST/GET/body or session."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    device_id = request.POST.get("device_id") or request.GET.get("device_id") or request.session.get(SESSION_DEVICE_KEY)
    if not device_id and request.content_type == "application/json":
        try:
            body = json.loads(request.body)
            device_id = body.get("device_id")
        except Exception:
            pass
    if device_id is not None:
        try:
            device_id = int(device_id)
        except (ValueError, TypeError):
            device_id = None
    device = _get_device(device_id)
    if not device:
        return JsonResponse({"success": False, "error": "No registered device"}, status=404)
    status_data, err = re_sync_device_from_get_status(device)
    if err:
        return JsonResponse({"success": False, "error": err}, status=400)
    service = DeviceApiService()
    config_data, config_err = service.get_config(device)
    return JsonResponse({
        "success": True,
        "last_fiscal_day_no": status_data.get("lastFiscalDayNo"),
        "last_receipt_global_no": status_data.get("lastReceiptGlobalNo"),
        "fiscal_day_status": status_data.get("fiscalDayStatus"),
        "configs_refreshed": config_err is None,
    })


@staff_member_required
def dashboard_status_api(request):
    """GET /api/dashboard/status/ or /api/fdms/status/ - JSON of getStatus for AJAX polling. Device from GET or session."""
    device = get_device_for_request(request)
    if not device:
        return JsonResponse(
            {"registered": False, "error": "No registered device"},
            status=404,
        )
    refresh = request.GET.get("refresh") == "1"
    if refresh:
        status_json, err = _fetch_status_for_dashboard(device)
        if err:
            return JsonResponse(
                {
                    "device_registered": True,
                    "device_id": device.device_id,
                    "fiscal_day_status": device.fiscal_day_status,
                    "last_fiscal_day_no": device.last_fiscal_day_no,
                    "last_receipt_global_no": device.last_receipt_global_no,
                    "fiscal_day_closing_error_code": getattr(device, "_closing_error", None),
                    "error": err,
                    "fetch_error": True,
                }
            )
        return JsonResponse(
            {
                "device_registered": True,
                "device_id": device.device_id,
                "fiscal_day_status": status_json.get("fiscalDayStatus"),
                "last_fiscal_day_no": status_json.get("lastFiscalDayNo"),
                "last_receipt_global_no": status_json.get("lastReceiptGlobalNo"),
                "fiscal_day_closing_error_code": status_json.get("fiscalDayClosingErrorCode"),
            }
        )
    return JsonResponse(
        {
            "device_registered": True,
            "device_id": device.device_id,
            "fiscal_day_status": device.fiscal_day_status,
            "last_fiscal_day_no": device.last_fiscal_day_no,
            "last_receipt_global_no": device.last_receipt_global_no,
            "fiscal_day_closing_error_code": None,
        }
    )


@staff_member_required
def api_fdms_status(request):
    """GET /api/fdms/status/ - fetch live getStatus from FDMS. Device from GET or session."""
    device = get_device_for_request(request)
    if not device or not device.is_registered:
        return JsonResponse({"error": "FDMS unreachable"}, status=500)

    from fiscal.services.fdms_device_service import FDMSDeviceService, FDMSDeviceError
    service = FDMSDeviceService()
    try:
        status_json = service.get_status(device)
    except FDMSDeviceError:
        return JsonResponse({"error": "FDMS unreachable"}, status=500)
    except Exception:
        return JsonResponse({"error": "FDMS unreachable"}, status=500)

    return JsonResponse(
        {
            "fiscalDayStatus": status_json.get("fiscalDayStatus"),
            "lastFiscalDayNo": status_json.get("lastFiscalDayNo"),
            "lastReceiptGlobalNo": status_json.get("lastReceiptGlobalNo"),
            "closingErrorCode": status_json.get("fiscalDayClosingErrorCode"),
        }
    )


@staff_member_required
def receipt_history(request):
    """Receipt submission history page. Tenant-scoped when request.tenant is set."""
    tenant = getattr(request, "tenant", None)
    device_id = request.GET.get("device_id", "").strip()
    current = get_device_for_request(request)
    queryset = Receipt.objects.all()
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    queryset = queryset.select_related("device").order_by("-created_at")
    if device_id and device_id.isdigit():
        queryset = queryset.filter(device__device_id=int(device_id))
    receipts = list(queryset[:200])
    devices_qs = FiscalDevice.objects.filter(is_registered=True)
    if tenant is not None:
        devices_qs = devices_qs.filter(tenant=tenant)
    devices = devices_qs.order_by("device_id")
    selected_device_id = int(device_id) if device_id and device_id.isdigit() else None
    return render(
        request,
        "fiscal/receipt_history.html",
        {
            "receipts": receipts,
            "devices": devices,
            "filters": {"device_id": device_id, "selected_device_id": selected_device_id},
        },
    )


@staff_member_required
def fiscal_day_dashboard(request):
    """Fiscal day state dashboard: devices and fiscal days overview. Tenant-scoped when request.tenant is set."""
    tenant = getattr(request, "tenant", None)
    devices_qs = FiscalDevice.objects.filter(is_registered=True)
    if tenant is not None:
        devices_qs = devices_qs.filter(tenant=tenant)
    devices = devices_qs.order_by("device_id")
    fiscal_days_qs = FiscalDay.objects.select_related("device").order_by("-opened_at")
    if tenant is not None:
        fiscal_days_qs = fiscal_days_qs.filter(tenant=tenant)
    fiscal_days = list(fiscal_days_qs[:100])
    return render(
        request,
        "fiscal/fiscal_day_dashboard.html",
        {
            "devices": devices,
            "fiscal_days": fiscal_days,
        },
    )


@staff_member_required
def fdms_logs(request):
    """FDMS API logs page: last 100 entries, filters, expandable payloads. Tenant-scoped when request.tenant is set."""
    from datetime import datetime

    from fiscal.models import FDMSApiLog
    from fiscal.utils import safe_json_dumps

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
    if status_code:
        try:
            sc = int(status_code)
            queryset = queryset.filter(status_code=sc)
        except ValueError:
            pass

    date_from = request.GET.get("date_from", "").strip()
    if date_from:
        try:
            dt = datetime.strptime(date_from, "%Y-%m-%d")
            queryset = queryset.filter(created_at__date__gte=dt.date())
        except ValueError:
            pass

    date_to = request.GET.get("date_to", "").strip()
    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d")
            queryset = queryset.filter(created_at__date__lte=dt.date())
        except ValueError:
            pass

    logs = list(queryset[:100])
    for log in logs:
        log.request_json = safe_json_dumps(log.request_payload) if log.request_payload else ""
        log.response_json = safe_json_dumps(log.response_payload) if log.response_payload else ""

    return render(
        request,
        "fiscal/fdms_logs.html",
        {
            "logs": logs,
            "debug_mode": settings.DEBUG,
            "filters": {
                "endpoint": endpoint,
                "operation_id": operation_id,
                "status_code": status_code,
                "date_from": date_from,
                "date_to": date_to,
            },
        },
    )


@staff_member_required
def device_register(request):
    """Device registration page: capture Device ID, Activation Key, Serial No."""
    form = DeviceRegistrationForm()
    success_message = None
    error_message = None
    device_status = None
    device_id = None

    if request.method == "POST":
        form = DeviceRegistrationForm(request.POST)
        if form.is_valid():
            service = DeviceRegistrationService()
            device, err = service.register_device(
                device_id=form.cleaned_data["device_id"],
                activation_key=form.cleaned_data["activation_key"],
                device_serial_no=form.cleaned_data["device_serial_no"].strip(),
                device_model_name=form.cleaned_data["device_model_name"].strip(),
                device_model_version=form.cleaned_data["device_model_version"].strip(),
            )
            if err:
                error_message = err
            else:
                success_message = f"Device {device.device_id} registered successfully."
                device_id = device.device_id
        else:
            error_message = "Please correct the errors below."

    if device_id:
        try:
            dev = FiscalDevice.objects.get(device_id=device_id)
            device_status = (
                f"Device {dev.device_id} is registered. "
                f"Certificate stored: Yes. Status: {'Active' if dev.is_registered else 'Inactive'}."
            )
        except FiscalDevice.DoesNotExist:
            pass
    elif request.GET.get("device_id"):
        try:
            dev = FiscalDevice.objects.get(device_id=int(request.GET["device_id"]))
            device_status = (
                f"Device {dev.device_id}: Registered={dev.is_registered}, "
                f"Certificate stored: Yes."
            )
        except (FiscalDevice.DoesNotExist, ValueError):
            device_status = "Device not found."

    return render(
        request,
        "fiscal/device_register.html",
        {
            "form": form,
            "success_message": success_message,
            "error_message": error_message,
            "device_status": device_status,
            "device_id": device_id,
        },
    )


from decimal import Decimal
from typing import Dict, Any, List


def build_credit_note_payload(
    device_id: int,
    fiscal_day_no: int,
    receipt_counter: int,
    original_receipt_global_no: int,
    original_receipt_date: str,
    currency: str,
    tax_percent: Decimal,
    sales_amount_with_tax: Decimal,
    tax_amount: Decimal,
    payment_amount: Decimal,
    reason: str,
) -> Dict[str, Any]:
    """
    Build FDMS credit note payload.
    """

    return {
        "receiptType": "CreditNote",
        "deviceID": device_id,
        "fiscalDayNo": fiscal_day_no,
        "receiptCounter": receipt_counter,
        "currency": currency,
        "originalReceipt": {
            "receiptGlobalNo": original_receipt_global_no,
            "receiptDate": original_receipt_date,
        },
        "receiptLines": [
            {
                "receiptLineType": "Credit",
                "receiptLineName": reason,
                "receiptLineTaxPercent": float(tax_percent),
                "receiptLineTotal": float(sales_amount_with_tax),
            }
        ],
        "receiptTaxes": [
            {
                "taxPercent": float(tax_percent),
                "taxAmount": float(tax_amount),
            }
        ],
        "receiptPayments": [
            {
                "moneyType": "CASH",
                "paymentAmount": float(payment_amount),
            }
        ],
        "totalAmount": float(sales_amount_with_tax),
    }


from collections import defaultdict
from decimal import Decimal
from typing import List, Dict, Any


def build_fiscal_day_counters(receipts: List[Any]) -> List[Dict[str, Any]]:
    """
    Build CloseDay fiscal counters from receipts.
    """

    sale_by_tax = defaultdict(Decimal)
    sale_tax_by_tax = defaultdict(Decimal)
    credit_by_tax = defaultdict(Decimal)
    credit_tax_by_tax = defaultdict(Decimal)
    debit_by_tax = defaultdict(Decimal)
    debit_tax_by_tax = defaultdict(Decimal)
    balance_by_money = defaultdict(Decimal)

    for r in receipts:

        key = (r.currency, r.tax_percent)

        if r.document_type == "INVOICE":
            sale_by_tax[key] += r.total
            sale_tax_by_tax[key] += r.tax_amount
            balance_by_money[(r.currency, r.money_type)] += r.total

        elif r.document_type == "CREDIT_NOTE":
            credit_by_tax[key] += r.total
            credit_tax_by_tax[key] += r.tax_amount
            balance_by_money[(r.currency, r.money_type)] -= r.total

        elif r.document_type == "DEBIT_NOTE":
            debit_by_tax[key] += r.total
            debit_tax_by_tax[key] += r.tax_amount
            balance_by_money[(r.currency, r.money_type)] += r.total

    counters = []

    # Sale
    for (currency, tax_percent), value in sale_by_tax.items():
        if value != 0:
            counters.append({
                "fiscalCounterType": "saleByTax",
                "fiscalCounterCurrency": currency,
                "fiscalCounterTaxPercent": float(tax_percent),
                "fiscalCounterValue": float(value),
            })

    for (currency, tax_percent), value in sale_tax_by_tax.items():
        if value != 0:
            counters.append({
                "fiscalCounterType": "saleTaxByTax",
                "fiscalCounterCurrency": currency,
                "fiscalCounterTaxPercent": float(tax_percent),
                "fiscalCounterValue": float(value),
            })

    # Credit
    for (currency, tax_percent), value in credit_by_tax.items():
        if value != 0:
            counters.append({
                "fiscalCounterType": "creditNoteByTax",
                "fiscalCounterCurrency": currency,
                "fiscalCounterTaxPercent": float(tax_percent),
                "fiscalCounterValue": float(value),
            })

    for (currency, tax_percent), value in credit_tax_by_tax.items():
        if value != 0:
            counters.append({
                "fiscalCounterType": "creditNoteTaxByTax",
                "fiscalCounterCurrency": currency,
                "fiscalCounterTaxPercent": float(tax_percent),
                "fiscalCounterValue": float(value),
            })

    # Debit
    for (currency, tax_percent), value in debit_by_tax.items():
        if value != 0:
            counters.append({
                "fiscalCounterType": "debitNoteByTax",
                "fiscalCounterCurrency": currency,
                "fiscalCounterTaxPercent": float(tax_percent),
                "fiscalCounterValue": float(value),
            })

    for (currency, tax_percent), value in debit_tax_by_tax.items():
        if value != 0:
            counters.append({
                "fiscalCounterType": "debitNoteTaxByTax",
                "fiscalCounterCurrency": currency,
                "fiscalCounterTaxPercent": float(tax_percent),
                "fiscalCounterValue": float(value),
            })

    # Balance
    for (currency, money_type), value in balance_by_money.items():
        if value != 0:
            counters.append({
                "fiscalCounterType": "balanceByMoneyType",
                "fiscalCounterCurrency": currency,
                "fiscalCounterMoneyType": money_type,
                "fiscalCounterValue": float(value),
            })

    return counters


from decimal import Decimal


def validate_credit_note(original_invoice, credit_total: Decimal) -> None:
    """
    Prevent illegal credit note.
    """

    if original_invoice is None:
        raise ValueError("Original invoice does not exist.")

    if original_invoice.is_void:
        raise ValueError("Cannot credit a voided invoice.")

    if credit_total <= 0:
        raise ValueError("Credit amount must be positive.")

    if credit_total > original_invoice.remaining_balance:
        raise ValueError("Credit exceeds remaining invoice balance.")


def validate_debit_note(original_invoice, debit_total: Decimal) -> None:
    """
    Prevent illegal debit note.
    """

    if original_invoice is None:
        raise ValueError("Original invoice does not exist.")

    if original_invoice.is_void:
        raise ValueError("Cannot debit a voided invoice.")

    if debit_total <= 0:
        raise ValueError("Debit amount must be positive.")


from decimal import Decimal
from typing import List, Dict


TYPE_ORDER = {
    "saleByTax": 1,
    "saleTaxByTax": 2,
    "creditNoteByTax": 3,
    "creditNoteTaxByTax": 4,
    "debitNoteByTax": 5,
    "debitNoteTaxByTax": 6,
    "balanceByMoneyType": 7,
}


def format_tax_percent(value: Decimal) -> str:
    return f"{value:.2f}"


def amount_to_cents(value: Decimal) -> str:
    return str(int(value * 100))


def build_close_day_canonical(
    device_id: int,
    fiscal_day_no: int,
    fiscal_day_date: str,
    counters: List[Dict],
) -> str:

    # Remove zero counters
    counters = [c for c in counters if Decimal(str(c["fiscalCounterValue"])) != 0]

    # Sort properly
    counters.sort(
        key=lambda c: (
            TYPE_ORDER[c["fiscalCounterType"]],
            c["fiscalCounterCurrency"],
            c.get("fiscalCounterTaxPercent", 0),
            c.get("fiscalCounterMoneyType", "")
        )
    )

    canonical = f"{device_id}{fiscal_day_no}{fiscal_day_date}"

    for c in counters:

        counter_type = c["fiscalCounterType"].upper()
        currency = c["fiscalCounterCurrency"].upper()
        amount = amount_to_cents(Decimal(str(c["fiscalCounterValue"])))

        canonical += counter_type
        canonical += currency

        if "fiscalCounterTaxPercent" in c:
            tax_percent = format_tax_percent(Decimal(str(c["fiscalCounterTaxPercent"])))
            canonical += tax_percent
        else:
            money_type = c["fiscalCounterMoneyType"].upper()
            canonical += money_type

        canonical += amount

    return canonical

