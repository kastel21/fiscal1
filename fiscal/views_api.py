"""JSON API endpoints for React dashboard. Never return private key or decrypted key."""

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from fiscal.models import FiscalDevice, QuickBooksEvent, QuickBooksInvoice, Receipt
from fiscal.utils import redact_for_ui

from .views import _fetch_status_for_dashboard, get_device_for_request


@staff_member_required
def api_devices_list(request):
    """GET /api/devices/ - List registered devices for invoice form. Tenant-scoped when request.tenant is set."""
    tenant = getattr(request, "tenant", None)
    qs = FiscalDevice.objects.filter(is_registered=True)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    devices = qs.order_by("device_id")
    data = [
        {
            "device_id": d.device_id,
            "fiscal_day_status": d.fiscal_day_status,
            "last_fiscal_day_no": d.last_fiscal_day_no,
            "is_vat_registered": bool(d.is_vat_registered),
        }
        for d in devices
    ]
    return JsonResponse({"devices": data})


@staff_member_required
def api_fdms_dashboard(request):
    """GET /api/fdms/dashboard/ - JSON for React dashboard."""
    device = get_device_for_request(request)
    device_data = {"deviceID": None, "status": "No device", "certExpiry": None}
    fiscal_data = {"dayNo": None, "status": None, "receiptCount": 0}
    last_receipt_data = {"globalNo": None, "total": None, "serverVerified": False}

    if device and device.is_registered:
        device_data["deviceID"] = device.device_id
        device_data["status"] = "Registered"
        device_data["certExpiry"] = device.certificate_valid_till.strftime("%Y-%m-%d") if device.certificate_valid_till else None

        status_json, _ = _fetch_status_for_dashboard(device)
        if status_json:
            fiscal_data["dayNo"] = status_json.get("lastFiscalDayNo")
            fiscal_data["status"] = status_json.get("fiscalDayStatus")
        fiscal_data["receiptCount"] = Receipt.objects.filter(
            device=device, fiscal_day_no=device.last_fiscal_day_no or 0
        ).count()

        last_rec = Receipt.objects.filter(device=device).order_by("-created_at").first()
        if last_rec:
            last_receipt_data["globalNo"] = last_rec.receipt_global_no
            last_receipt_data["total"] = str(last_rec.receipt_total) if last_rec.receipt_total else None
            last_receipt_data["serverVerified"] = bool(last_rec.receipt_server_signature)

    return JsonResponse({
        "device": device_data,
        "fiscal": fiscal_data,
        "lastReceipt": last_receipt_data,
    })


@staff_member_required
def api_fdms_receipts(request):
    """GET /api/fdms/receipts/ - JSON list of receipts. Never allow deletion. Tenant-scoped when request.tenant is set."""
    tenant = getattr(request, "tenant", None)
    device_id = request.GET.get("device_id")
    queryset = Receipt.objects.all()
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    if device_id and str(device_id).isdigit():
        queryset = queryset.filter(device_id=int(device_id))
    queryset = queryset.select_related("device").order_by("-created_at")[:100]
    receipts = []
    for r in queryset:
        receipts.append({
            "id": r.pk,
            "deviceId": r.device.device_id,
            "fiscalDayNo": r.fiscal_day_no,
            "receiptGlobalNo": r.receipt_global_no,
            "invoiceNo": r.invoice_no or "",
            "receiptType": r.receipt_type,
            "total": str(r.receipt_total) if r.receipt_total else None,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        })
    return JsonResponse({"receipts": receipts})


@staff_member_required
def api_fdms_fiscal(request):
    """GET /api/fdms/fiscal/ - JSON fiscal day status."""
    device = get_device_for_request(request)
    data = {"dayNo": None, "status": None, "lastReceiptGlobalNo": None, "error": None}
    if not device or not device.is_registered:
        data["error"] = "No registered device"
        return JsonResponse(data)
    status_json, err = _fetch_status_for_dashboard(device)
    if err:
        data["error"] = err
        data["status"] = device.fiscal_day_status
        data["dayNo"] = device.last_fiscal_day_no
        data["lastReceiptGlobalNo"] = device.last_receipt_global_no
    elif status_json:
        data["dayNo"] = status_json.get("lastFiscalDayNo")
        data["status"] = status_json.get("fiscalDayStatus")
        data["lastReceiptGlobalNo"] = status_json.get("lastReceiptGlobalNo")
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(["POST"])
def api_qb_validate_invoice_update(request):
    """
    Validate QuickBooks Invoice.Update. Call from QB webhook handler.
    POST body: { "receipt_id": int, "invoice": {...} } or { "invoice_no": str, "invoice": {...} }
    Returns 200 { "allowed": true } or 403 { "allowed": false, "reason": "..." }
    """
    from fiscal.services.qb_edit_safeguards import validate_qb_invoice_update

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"allowed": False, "reason": "Invalid JSON"}, status=400)

    receipt_id = body.get("receipt_id")
    invoice_no = body.get("invoice_no")
    invoice = body.get("invoice") or body.get("payload") or body

    tenant = getattr(request, "tenant", None)
    receipt = None
    if receipt_id:
        q = Receipt.objects.filter(pk=receipt_id)
        if tenant is not None:
            q = q.filter(tenant=tenant)
        receipt = q.first()
    elif invoice_no:
        q = Receipt.objects.filter(invoice_no=invoice_no)
        if tenant is not None:
            q = q.filter(tenant=tenant)
        receipt = q.first()

    if not receipt:
        return JsonResponse({"allowed": False, "reason": "Receipt not found"}, status=404)

    actor = body.get("actor") or request.META.get("HTTP_X_QB_REALM_ID") or ""
    allowed, reason = validate_qb_invoice_update(
        receipt=receipt,
        attempted_payload=invoice,
        source="QB",
        actor=str(actor),
    )
    if allowed:
        return JsonResponse({"allowed": True})
    return JsonResponse({"allowed": False, "reason": reason}, status=403)


@csrf_exempt
@require_http_methods(["POST"])
def api_qb_webhook(request):
    """
    QuickBooks webhook. POST /api/integrations/quickbooks/webhook
    Accepts: (a) QB webhook format with eventNotifications or CloudEvents
    (b) Full invoice JSON for direct fiscalisation (adapter forwards invoice).
    ACK fast. Persist raw payload. If full invoice present, fiscalise.
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    if isinstance(body, list):
        body = {"_cloud_events": body}

    event_type = "unknown"
    invoice_id = None
    invoice_payload = None

    if "_cloud_events" in body:
        events = body["_cloud_events"]
        if events:
            ev = events[0]
            event_type = ev.get("type", "unknown")
            invoice_id = ev.get("intuitentityid") or ev.get("intuitEntityId")
    elif "eventNotifications" in body:
        for notif in body.get("eventNotifications", []):
            dce = notif.get("dataChangeEvent", {})
            for ent in dce.get("entities", []):
                if ent.get("name") == "Invoice" and ent.get("operation") == "Create":
                    event_type = "Invoice.Create"
                    invoice_id = ent.get("id")
                    break

    if (body.get("Line") or body.get("TotalAmt") or body.get("Id")) and not invoice_id:
        invoice_payload = body
        invoice_id = str(body.get("Id", ""))
        event_type = "Invoice.Create" if invoice_id else "unknown"

    QuickBooksEvent.objects.create(event_type=event_type, payload=body)

    if invoice_payload and invoice_id:
        from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice
        qb_inv, err = fiscalise_qb_invoice(invoice_id, invoice_payload)
        if qb_inv and qb_inv.fiscalised:
            return JsonResponse({
                "status": "ok",
                "fiscalised": True,
                "qb_invoice_id": invoice_id,
                "receipt_global_no": qb_inv.fiscal_receipt.receipt_global_no if qb_inv.fiscal_receipt else None,
            })
        return JsonResponse({
            "status": "received",
            "fiscalised": False,
            "qb_invoice_id": invoice_id,
            "error": err or qb_inv.fiscal_error if qb_inv else None,
        })

    return JsonResponse({"status": "received", "event_type": event_type, "invoice_id": invoice_id})


@csrf_exempt
@require_http_methods(["POST"])
def api_qb_webhook_verified(request):
    """
    QuickBooks webhook with HMAC verification. POST /api/qb/webhook/
    Verify intuit-signature, parse eventNotifications, for each Invoice/CreditMemo Create
    call handle_qb_event (fetch from QB API, create Receipt PENDING, queue fiscalisation).
    Respond quickly with {"status": "ok"}. No fiscalisation in request path.
    """
    raw_body = request.body
    if raw_body is None:
        raw_body = b""
    signature_header = request.META.get("HTTP_INTUIT_SIGNATURE") or request.headers.get("intuit-signature", "")

    from fiscal.services.qb_service import verify_qb_webhook_signature, handle_qb_event

    if not verify_qb_webhook_signature(raw_body, signature_header):
        return JsonResponse({"status": "error", "message": "Invalid signature"}, status=401)

    try:
        body = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    event_notifications = body.get("eventNotifications") or []
    for notif in event_notifications:
        dce = notif.get("dataChangeEvent") or {}
        realm_id = str(dce.get("realmId") or body.get("realmId") or "")
        entities = dce.get("entities") or []
        for entity in entities:
            name = entity.get("name")
            operation = entity.get("operation")
            entity_id = entity.get("id")
            if name in ("Invoice", "CreditMemo") and operation == "Create" and entity_id:
                handle_qb_event(name, str(entity_id), realm_id)

    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_http_methods(["POST"])
def api_qb_fiscalise_invoice(request):
    """
    POST /api/integrations/quickbooks/invoice - Fiscalise QB invoice from full JSON.
    Use when adapter fetches invoice from QB and forwards. Idempotent by qb_invoice_id.
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    invoice_id = str(body.get("Id", body.get("qb_invoice_id", "")))
    if not invoice_id:
        return JsonResponse({"success": False, "error": "Missing invoice Id"}, status=400)

    from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice
    qb_inv, err = fiscalise_qb_invoice(invoice_id, body)

    if not qb_inv:
        return JsonResponse({"success": False, "error": redact_for_ui(err or "")}, status=500)

    if qb_inv.fiscalised:
        return JsonResponse({
            "success": True,
            "fiscalised": True,
            "qb_invoice_id": invoice_id,
            "receipt_global_no": qb_inv.fiscal_receipt.receipt_global_no,
            "receipt_id": qb_inv.fiscal_receipt.fdms_receipt_id,
            "private_note": f"Fiscalised: GlobalNo {qb_inv.fiscal_receipt.receipt_global_no:06d} | QR available",
        })

    return JsonResponse({
        "success": False,
        "fiscalised": False,
        "qb_invoice_id": invoice_id,
        "error": redact_for_ui(err or qb_inv.fiscal_error or ""),
        "status": "PENDING_FISCALISATION",
    }, status=202)


@staff_member_required
def api_qb_invoices(request):
    """GET /api/integrations/quickbooks/invoices - List QB invoices for UI."""
    qs = QuickBooksInvoice.objects.select_related("fiscal_receipt").order_by("-created_at")[:100]
    invoices = []
    for inv in qs:
        invoices.append({
            "id": inv.id,
            "qb_invoice_id": inv.qb_invoice_id,
            "fiscalised": inv.fiscalised,
            "receipt_global_no": inv.fiscal_receipt.receipt_global_no if inv.fiscal_receipt else None,
            "receipt_id": inv.fiscal_receipt.fdms_receipt_id if inv.fiscal_receipt else None,
            "fiscal_error": inv.fiscal_error or None,
            "total_amount": str(inv.total_amount) if inv.total_amount else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        })
    return JsonResponse({"invoices": invoices})


@staff_member_required
def api_qb_oauth_connect(request):
    """Redirect to Intuit OAuth authorize URL."""
    from fiscal.services.qb_oauth import get_authorize_url
    url = get_authorize_url(request=request)
    if not url:
        return JsonResponse({"error": "QB_CLIENT_ID not configured"}, status=400)
    from django.shortcuts import redirect
    return redirect(url)


@staff_member_required
def api_qb_oauth_callback(request):
    """OAuth callback - exchange code for tokens."""
    from django.shortcuts import redirect
    from fiscal.services.qb_oauth import exchange_code_for_tokens, get_redirect_uri
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    if not code or not realm_id:
        return redirect("fdms_qb_invoices")
    redirect_uri = get_redirect_uri(request)
    data, err = exchange_code_for_tokens(code, redirect_uri, realm_id)
    if err:
        return JsonResponse({"error": redact_for_ui(err)}, status=400)
    return redirect("fdms_qb_invoices")


@staff_member_required
@require_http_methods(["POST"])
def api_qb_sync(request):
    """Trigger sync from QuickBooks - fetch and fiscalise."""
    from fiscal.services.qb_sync import sync_from_quickbooks
    result = sync_from_quickbooks(max_per_type=50)
    if "error" in result:
        return JsonResponse({**result, "error": redact_for_ui(result.get("error", ""))}, status=400)
    return JsonResponse(result)


@staff_member_required
@require_http_methods(["POST"])
def api_qb_retry_fiscalise(request):
    """POST /api/integrations/quickbooks/retry - Retry fiscalisation for pending QB invoice."""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    qb_invoice_id = body.get("qb_invoice_id")
    if not qb_invoice_id:
        return JsonResponse({"success": False, "error": "Missing qb_invoice_id"}, status=400)

    inv = QuickBooksInvoice.objects.filter(qb_invoice_id=qb_invoice_id).first()
    if not inv:
        return JsonResponse({"success": False, "error": "Invoice not found"}, status=404)
    if inv.fiscalised:
        return JsonResponse({"success": True, "fiscalised": True, "message": "Already fiscalised"})

    from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice
    qb_inv, err = fiscalise_qb_invoice(qb_invoice_id, inv.raw_payload)

    if qb_inv and qb_inv.fiscalised:
        return JsonResponse({
            "success": True,
            "fiscalised": True,
            "receipt_global_no": qb_inv.fiscal_receipt.receipt_global_no,
        })
    return JsonResponse({
        "success": False,
        "fiscalised": False,
        "error": redact_for_ui(err or (qb_inv.fiscal_error if qb_inv else "") or ""),
    }, status=400)
