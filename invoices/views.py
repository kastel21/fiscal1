"""Invoice creation API views."""

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse

from fiscal.services.fdms_events import emit_metrics_updated

from .serializers import ValidationError, validate_invoice_create
from .services import create_invoice


@staff_member_required
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
    receipt, err = create_invoice(validated)
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
