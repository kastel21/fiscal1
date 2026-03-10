"""Invoice creation API views."""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from fiscal.models import FiscalDevice
from fiscal.services.fdms_events import emit_metrics_updated
from fiscal.utils import validate_device_for_tenant

from .serializers import ValidationError, validate_invoice_create
from .services import create_invoice


@login_required
def invoice_create_api(request):
    """POST /api/invoices/ - Create and submit invoice to FDMS."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    try:
        validated = validate_invoice_create(body)
    except ValidationError as e:
        return JsonResponse({"error": e.message, "field": e.field}, status=400)

    tenant = getattr(request, "tenant", None)
    if tenant:
        device = FiscalDevice.objects.filter(
            tenant=tenant,
            device_id=validated["device_id"],
            is_registered=True,
        ).first()
        if not device:
            return JsonResponse({"error": "Device not found or not for this tenant"}, status=403)
        validate_device_for_tenant(device, tenant)
        validated["tenant_id"] = str(tenant.id)

    try:
        receipt, err = create_invoice(validated)
    except Exception as e:
        import logging
        logging.getLogger("invoices").exception("create_invoice failed")
        return JsonResponse({"error": str(e)}, status=400)
    if err:
        return JsonResponse({"error": err}, status=400)
    emit_metrics_updated()
    return JsonResponse({
        "success": True,
        "receipt_id": receipt.fdms_receipt_id,
        "receipt_global_no": receipt.receipt_global_no,
        "receipt_counter": receipt.receipt_counter,
        "invoice_no": receipt.invoice_no or "",
    })
