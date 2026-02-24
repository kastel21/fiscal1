"""
Views for Credit Note and Debit Note form-based creation.
"""

import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from fiscal.forms import CreditNoteForm, DebitNoteForm
from fiscal.services.config_service import get_config_status
from fiscal.services.credit_note_import_service import get_enriched_invoices_for_form
from fiscal.services.credit_note_service import create_credit_note
from fiscal.services.debit_note_service import create_debit_note
from fiscal.views import get_device_for_request


def _serialize_invoices(invoices: list) -> str:
    """Serialize enriched invoices for JS. Ensures floats for numeric fields."""
    out = []
    for inv in invoices:
        lines = inv.get("lines", [])
        for ln in lines:
            for k in ("receiptLineQuantity", "receiptLineTotal", "receiptLinePrice", "taxPercent", "receiptLineTaxPercent"):
                if k in ln and ln[k] is not None:
                    try:
                        ln[k] = float(ln[k])
                    except (TypeError, ValueError):
                        pass
        out.append({
            "id": inv.get("id"),
            "invoice_no": inv.get("invoice_no", ""),
            "receipt_global_no": inv.get("receipt_global_no"),
            "currency": inv.get("currency", "USD"),
            "total": float(inv.get("total", 0)),
            "remaining_balance": float(inv.get("remaining_balance", 0)),
            "date": inv.get("date", ""),
            "customer": inv.get("customer", ""),
            "lines": lines,
            "tax_percent": float(inv.get("tax_percent", 0)),
        })
    return json.dumps(out)


@staff_member_required
@require_http_methods(["GET", "POST"])
def credit_note_form_view(request):
    """Credit Note form: select invoice, reason, items, refund method."""
    device = get_device_for_request(request)
    if not device:
        return redirect("fdms_dashboard")

    config_status = get_config_status(device.device_id)["status"]
    can_submit = config_status == "OK"
    invoices = get_enriched_invoices_for_form(device, limit=500)
    invoices_json = _serialize_invoices(invoices)

    form = CreditNoteForm(device=device, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        credit_lines = form.cleaned_data["_credit_lines"]
        credit_total = form.cleaned_data["_credit_total"]
        reason = form.cleaned_data["_reason_text"]
        refund_method = form.cleaned_data.get("refund_method", "CASH") or "CASH"
        original = form._original_receipt
        customer_snapshot = original.customer_snapshot or {}

        debug_capture = {}
        receipt, err = create_credit_note(
            original_receipt=original,
            credit_lines=credit_lines,
            credit_total=credit_total,
            reason=reason,
            customer_snapshot=customer_snapshot,
            refund_method=refund_method,
            debug_capture=debug_capture,
        )
        submit_debug = None
        if debug_capture and "request" in debug_capture:
            submit_debug = {
                "request": debug_capture.get("request", ""),
                "response_status": debug_capture.get("response_status", "—"),
                "response": debug_capture.get("response", "(No response received – check server logs)"),
            }
        if err:
            messages.error(request, err)
            return render(request, "fiscal/credit_note_form.html", {
                "form": form,
                "invoices": invoices,
                "invoices_json": invoices_json,
                "can_submit_receipt": can_submit,
                "config_status": config_status,
                "submit_debug": submit_debug,
                "error_message": err,
            })
        messages.success(request, f"Credit note {receipt.invoice_no} created successfully.")
        if submit_debug:
            request.session["last_submit_debug"] = {
                "receipt_id": receipt.pk,
                **submit_debug,
            }
        return redirect("fdms_receipt_detail", pk=receipt.pk)

    error_message = None
    if request.method == "POST" and form.errors:
        error_message = "Please correct the errors below."
        if form.non_field_errors():
            error_message = str(form.non_field_errors()[0])
        elif form.errors.get("credit_line_data"):
            error_message = str(form.errors["credit_line_data"][0])
        elif form.errors.get("original_invoice_id"):
            error_message = str(form.errors["original_invoice_id"][0])
        elif form.errors.get("credit_reason"):
            error_message = str(form.errors["credit_reason"][0])
        elif form.errors.get("credit_reason_other"):
            error_message = str(form.errors["credit_reason_other"][0])
    return render(request, "fiscal/credit_note_form.html", {
        "form": form,
        "invoices": invoices,
        "invoices_json": invoices_json,
        "can_submit_receipt": can_submit,
        "config_status": config_status,
        "submit_debug": None,
        "error_message": error_message,
    })


@staff_member_required
def api_credit_note_form_invoices(request):
    """GET /api/credit-note-form/invoices/ - Enriched invoices for credit note form dropdown."""
    device = get_device_for_request(request)
    if not device:
        return JsonResponse({"invoices": []})
    invoices = get_enriched_invoices_for_form(device, limit=500)
    out = []
    for inv in invoices:
        lines = inv.get("lines", [])
        for ln in lines:
            for k in ("receiptLineQuantity", "receiptLineTotal", "receiptLinePrice", "taxPercent", "receiptLineTaxPercent"):
                if k in ln and ln[k] is not None:
                    try:
                        ln[k] = float(ln[k])
                    except (TypeError, ValueError):
                        pass
        out.append({
            "id": inv.get("id"),
            "invoice_no": inv.get("invoice_no", ""),
            "receipt_global_no": inv.get("receipt_global_no"),
            "currency": inv.get("currency", "USD"),
            "total": float(inv.get("total", 0)),
            "remaining_balance": float(inv.get("remaining_balance", 0)),
            "date": inv.get("date", ""),
            "customer": inv.get("customer", ""),
            "lines": lines,
        })
    return JsonResponse({"invoices": out})


@staff_member_required
@require_http_methods(["GET", "POST"])
def debit_note_form_view(request):
    """Debit Note form: select invoice, reason, add lines or charge amount."""
    device = get_device_for_request(request)
    if not device:
        return redirect("fdms_dashboard")

    config_status = get_config_status(device.device_id)["status"]
    can_submit = config_status == "OK"
    invoices = get_enriched_invoices_for_form(device, limit=50, for_debit=True)
    invoices_json = _serialize_invoices(invoices)

    form = DebitNoteForm(device=device, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        debit_lines = form.cleaned_data["_debit_lines"]
        debit_total = form.cleaned_data["_debit_total"]
        reason = form.cleaned_data["debit_reason"]
        original = form._original_receipt
        customer_snapshot = original.customer_snapshot or {}

        receipt, err = create_debit_note(
            original_receipt=original,
            debit_lines=debit_lines,
            debit_total=debit_total,
            reason=reason,
            customer_snapshot=customer_snapshot,
        )
        if err:
            messages.error(request, err)
        else:
            messages.success(request, f"Debit note {receipt.invoice_no} created successfully.")
            return redirect("fdms_receipt_detail", pk=receipt.pk)

    return render(request, "fiscal/debit_note_form.html", {
        "form": form,
        "invoices_json": invoices_json,
        "can_submit_receipt": can_submit,
        "config_status": config_status,
    })


