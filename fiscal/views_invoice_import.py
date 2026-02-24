"""Invoice Excel import wizard. Invoice 01 / Laundry Bin / Flyquest spec."""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from fiscal.models import FiscalDevice, InvoiceImport, Receipt
from fiscal.views import get_device_for_request
from fiscal.services.config_service import get_config_status, get_latest_configs
from fiscal.services.excel_parser import list_and_rank_sheets, parse_excel, validate_line_math
from fiscal.services.invoice_import_service import lines_to_receipt_payload, validate_invoice_import
from fiscal.services.receipt_service import submit_receipt


@staff_member_required
def invoice_import_step1(request):
    """Step 1: File upload, sheet selection."""
    device = get_device_for_request(request)
    if not device:
        return render(request, "fdms/invoice_import/step1.html", {"error": "No registered device."})
    error = None
    sheets = []
    if request.method == "POST":
        if request.FILES.get("excel_file"):
            f = request.FILES["excel_file"]
            content = f.read()
            try:
                sheets = list_and_rank_sheets(content)
                request.session["invoice_import_excel"] = content
                request.session["invoice_import_filename"] = f.name
                selected = request.POST.get("sheet_name")
                if selected and any(s["name"] == selected and s["importable"] for s in sheets):
                    lines, meta = parse_excel(content, sheet_name=selected)
                    if meta.get("error"):
                        error = meta["error"]
                    else:
                        request.session["invoice_import_sheet"] = selected
                        request.session["invoice_import_lines"] = lines
                        request.session["invoice_import_meta"] = meta
                        return redirect("fdms_invoice_import_preview")
                elif not sheets:
                    error = "Could not read workbook."
                elif not any(s["importable"] for s in sheets):
                    error = "No importable sheet found. Allowed: Invoice 01. Ignored: quote, Delivery Note."
            except Exception as e:
                error = str(e)
        elif request.session.get("invoice_import_excel") and request.POST.get("sheet_name"):
            selected = request.POST["sheet_name"]
            content = request.session["invoice_import_excel"]
            sheets = list_and_rank_sheets(content)
            if any(s["name"] == selected and s["importable"] for s in sheets):
                lines, meta = parse_excel(content, sheet_name=selected)
                if not meta.get("error"):
                    request.session["invoice_import_sheet"] = selected
                    request.session["invoice_import_lines"] = lines
                    request.session["invoice_import_meta"] = meta
                    return redirect("fdms_invoice_import_preview")
                error = meta.get("error", "Parse error")

    if not sheets and request.session.get("invoice_import_excel"):
        try:
            sheets = list_and_rank_sheets(request.session["invoice_import_excel"])
        except Exception:
            pass

    return render(request, "fdms/invoice_import/step1.html", {
        "error": error,
        "sheets": sheets,
    })


@staff_member_required
def invoice_import_preview(request):
    """Step 2-3: Preview table + enrichment panel."""
    device = get_device_for_request(request)
    if not device:
        return redirect("fdms_invoice_import_step1")
    lines = request.session.get("invoice_import_lines")
    meta = request.session.get("invoice_import_meta", {})
    if not lines:
        return redirect("fdms_invoice_import_step1")

    config_status = get_config_status(device.device_id)["status"]
    configs = get_latest_configs(device.device_id)
    tax_options = []
    if configs and configs.tax_table:
        for t in configs.tax_table:
            tid = t.get("taxID")
            tname = t.get("taxName", "")
            if tid is not None:
                tax_options.append({"id": tid, "name": tname or f"Tax {tid}"})
    if not tax_options:
        tax_options = [{"id": 1, "name": "VAT 15%"}]

    if request.method == "POST":
        receipt_type = request.POST.get("receipt_type", "FiscalInvoice")
        currency = (request.POST.get("currency") or "USD").strip() or "USD"
        tax_id_raw = request.POST.get("tax_id")
        tax_id = int(tax_id_raw) if tax_id_raw and str(tax_id_raw).isdigit() else None
        confirm = request.POST.get("confirm_totals") == "on"

        validation_errors = validate_invoice_import(
            lines, receipt_type, currency, tax_id, device
        )
        if not confirm:
            validation_errors.append("You must confirm the computed totals.")
        if not validation_errors:
            receipt_lines, receipt_taxes, receipt_payments, total = lines_to_receipt_payload(
                lines, currency, tax_id or 1, receipt_lines_tax_inclusive=False
            )
            fiscal_day_no = device.last_fiscal_day_no
            if fiscal_day_no is None:
                validation_errors.append("No open fiscal day. Open a fiscal day first.")
            elif config_status != "OK":
                validation_errors.append("FDMS configs missing or stale.")
            else:
                receipt_obj, err = submit_receipt(
                    device=device,
                    fiscal_day_no=int(fiscal_day_no),
                    receipt_type=receipt_type,
                    receipt_currency=currency,
                    invoice_no=(request.POST.get("invoice_no") or "").strip() or "",
                    receipt_lines=receipt_lines,
                    receipt_taxes=receipt_taxes,
                    receipt_payments=receipt_payments,
                    receipt_total=total,
                    receipt_lines_tax_inclusive=False,
                )
                if err:
                    validation_errors.append(err)
                else:
                    InvoiceImport.objects.create(
                        sheet_name=meta.get("sheet_name", ""),
                        header_row=meta.get("header_row"),
                        parsed_lines=lines,
                        receipt_type=receipt_type,
                        currency=currency,
                        tax_id=tax_id,
                        user_confirmed=True,
                        fiscal_receipt=receipt_obj,
                    )
                    for k in list(request.session.keys()):
                        if k.startswith("invoice_import_"):
                            request.session.pop(k, None)
                    return redirect("fdms_invoice_import_success", pk=receipt_obj.pk)
    else:
        validation_errors = []
        for line in lines:
            validation_errors.extend(validate_line_math(line))

    subtotal = sum(float(l.get("line_total", 0)) for l in lines)
    return render(request, "fdms/invoice_import/preview.html", {
        "lines": lines,
        "meta": meta,
        "subtotal": subtotal,
        "tax_options": tax_options,
        "validation_errors": validation_errors,
        "config_status": config_status,
        "can_submit": config_status == "OK",
    })


@staff_member_required
def invoice_import_success(request, pk):
    tenant = getattr(request, "tenant", None)
    qs = Receipt.objects.filter(pk=pk)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    receipt = qs.first()
    return render(request, "fdms/invoice_import/success.html", {"receipt": receipt})


