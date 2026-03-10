"""Management module APIs: Company, Devices, Products."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import Company, Customer, FiscalDevice, Product, TaxMapping
from .utils import validate_device_for_tenant
from .services.config_service import (
    TAX_CODE_MAX_LENGTH,
    get_latest_configs,
    get_tax_id_to_percent,
    get_tax_table_from_configs,
)
from django.conf import settings
from .services.device_api import DeviceApiService


@login_required
@require_http_methods(["GET"])
def api_config_env(request):
    """GET /api/config/env/ - Returns FDMS environment (TEST, STAGING, PROD) for frontend banner."""
    fdms_env = getattr(settings, "FDMS_ENV", "TEST")
    return JsonResponse({"fdms_env": fdms_env})


@login_required
def api_config_taxes(request):
    """GET /api/config/taxes/ - Tax options. Use source=getconfig for FDMS tax dropdown on tax mapping form.
    Default: TaxMapping (invoice dropdown). source=getconfig: saved GetConfig applicableTaxes only."""
    device_id = request.GET.get("device_id")
    did = int(device_id) if device_id and str(device_id).isdigit() else None
    source_getconfig = request.GET.get("source", "").lower() == "getconfig"
    source_invoice = request.GET.get("source", "").lower() == "invoice"
    configs = get_latest_configs(did)
    device = FiscalDevice.all_objects.filter(device_id=did, is_registered=True).first() if did else None
    is_vat_registered = bool(device and device.is_vat_registered)

    # Invoice dropdown: FDMS applicableTaxes (Exempt, Zero rated, 514, 517)
    # Exempt (taxID 1): no taxPercent in response so canonical/payload treat as Exempt
    APPLICABLE_TAXES = [
        {"taxID": 1, "taxCode": "1", "taxName": "Exempt"},
        {"taxID": 2, "taxCode": "2", "taxPercent": 0.0, "taxName": "Zero rated 0%"},
        {"taxID": 514, "taxCode": "514", "taxPercent": 5.0, "taxName": "Non-VAT Withholding Tax"},
        {"taxID": 517, "taxCode": "517", "taxPercent": 15.5, "taxName": "Standard rated 15.5%"},
    ]
    if source_invoice:
        taxes = []
        for t in APPLICABLE_TAXES:
            out = {"taxID": t["taxID"], "taxCode": t["taxCode"], "taxName": t["taxName"]}
            if "taxPercent" in t and t["taxPercent"] is not None:
                out["taxPercent"] = format(round(float(t["taxPercent"]), 2), ".2f")
            else:
                out["taxPercent"] = None
            taxes.append(out)
        if not is_vat_registered:
            taxes = [t for t in taxes if t.get("taxPercent") is None or float(t.get("taxPercent") or 0) == 0]
        return JsonResponse({
            "taxes": taxes,
            "is_vat_registered": is_vat_registered,
            "configs_loaded": configs is not None,
        })
    id_to_pct = get_tax_id_to_percent(configs)

    # Tax mapping form: FDMS tax dropdown from saved GetConfig only
    if source_getconfig:
        tax_table = get_tax_table_from_configs(configs)
        taxes = []
        seen = set()
        for i, t in enumerate(tax_table):
            tid = t.get("taxID") if t.get("taxID") is not None else (i + 1)
            raw = t.get("taxCode")
            code = (str(raw).strip()[:TAX_CODE_MAX_LENGTH] if raw is not None else "") or str(t.get("taxName", "") or "").strip()[:TAX_CODE_MAX_LENGTH] or str(tid)
            if not code:
                code = str(tid)
            code_upper = code.upper()
            if code_upper in seen:
                continue
            seen.add(code_upper)
            out = {"taxID": int(tid) if tid is not None else (i + 1), "taxCode": code, "taxName": str(t.get("taxName", "") or code)}
            if "taxPercent" in t and t["taxPercent"] is not None:
                out["taxPercent"] = format(round(float(t["taxPercent"]), 2), ".2f")
            elif "fiscalCounterTaxPercent" in t and t["fiscalCounterTaxPercent"] is not None:
                out["taxPercent"] = format(round(float(t["fiscalCounterTaxPercent"]), 2), ".2f")
            else:
                out["taxPercent"] = None
            taxes.append(out)
        return JsonResponse({
            "taxes": taxes,
            "is_vat_registered": True,
            "configs_loaded": configs is not None,
        })

    # Obtain taxes from TaxMapping (primary source for invoice dropdown)
    taxes = []
    for m in TaxMapping.objects.filter(is_active=True).order_by("sort_order", "local_code"):
        code = str(m.local_code or "").strip()
        if not code:
            continue
        pct = float(m.tax_percent) if m.tax_percent is not None else id_to_pct.get(m.fdms_tax_id, 15.0)
        if not is_vat_registered and pct != 0:
            continue
        taxes.append({
            "taxID": m.fdms_tax_id,
            "taxCode": code,
            "taxPercent": format(round(float(pct), 2), ".2f"),
            "taxName": m.display_name or code,
        })

    # If no TaxMapping entries, fall back to GetConfig (applicableTaxes)
    if not taxes:
        tax_table = get_tax_table_from_configs(configs)
        seen = set()
        for i, t in enumerate(tax_table):
            tid = t.get("taxID") if t.get("taxID") is not None else (i + 1)
            raw = t.get("taxCode")
            code = (str(raw).strip()[:TAX_CODE_MAX_LENGTH] if raw is not None else "") or str(t.get("taxName", "") or "").strip()[:TAX_CODE_MAX_LENGTH] or str(tid)
            if not code:
                code = str(tid)
            code_upper = code.upper()
            if code_upper in seen:
                continue
            seen.add(code_upper)
            out = {"taxID": int(tid) if tid is not None else (i + 1), "taxCode": code, "taxName": str(t.get("taxName", "") or code)}
            if "taxPercent" in t and t["taxPercent"] is not None:
                out["taxPercent"] = format(round(float(t["taxPercent"]), 2), ".2f")
            elif "fiscalCounterTaxPercent" in t and t["fiscalCounterTaxPercent"] is not None:
                out["taxPercent"] = format(round(float(t["fiscalCounterTaxPercent"]), 2), ".2f")
            else:
                out["taxPercent"] = None
            taxes.append(out)
        if not taxes and configs:
            taxes = [{"taxID": 1, "taxCode": "1", "taxName": "Exempt", "taxPercent": None}, {"taxID": 517, "taxCode": "517", "taxPercent": "15.50", "taxName": "Standard rated 15.5%"}]

    if not is_vat_registered:
        taxes = [t for t in taxes if t.get("taxPercent") is None or float(t.get("taxPercent") or 0) == 0]
        if not taxes and configs:
            taxes = [{"taxID": 1, "taxCode": "1", "taxName": "Exempt", "taxPercent": None}, {"taxID": 2, "taxCode": "2", "taxPercent": "0.00", "taxName": "Zero rated 0%"}]

    if not taxes and did is not None:
        if not is_vat_registered:
            taxes = [{"taxID": 1, "taxCode": "1", "taxName": "Exempt", "taxPercent": None}, {"taxID": 2, "taxCode": "2", "taxPercent": "0.00", "taxName": "Zero rated 0%"}]
        else:
            taxes = []
            for t in APPLICABLE_TAXES:
                out = {"taxID": t["taxID"], "taxCode": t["taxCode"], "taxName": t["taxName"]}
                out["taxPercent"] = format(round(float(t["taxPercent"]), 2), ".2f") if t.get("taxPercent") is not None else None
                taxes.append(out)
    return JsonResponse({
        "taxes": taxes,
        "is_vat_registered": is_vat_registered,
        "configs_loaded": configs is not None,
    })


def _require_admin(request):
    """Only superuser or admin group."""
    if not request.user.is_authenticated:
        return False
    if request.user.is_superuser or request.user.is_staff:
        return True
    return request.user.groups.filter(name="admin").exists()


def _require_operator(request):
    """Operator or admin can create invoices."""
    return _require_admin(request) or request.user.groups.filter(name="operator").exists()


@login_required
@require_http_methods(["GET", "PUT"])
def api_company(request):
    """GET/PUT /api/company/ - Single company (first). Admin only."""
    if not _require_admin(request):
        return JsonResponse({"error": "Admin access required"}, status=403)
    company = Company.objects.first()
    if request.method == "GET":
        if not company:
            return JsonResponse({"company": None})
        return JsonResponse({
            "company": {
                "id": company.id,
                "name": company.name,
                "tin": company.tin,
                "vat_number": company.vat_number,
                "address": company.address,
                "phone": company.phone,
                "email": company.email,
                "currency_default": company.currency_default,
            }
        })
    body = json.loads(request.body or "{}")
    if not company:
        company = Company(
            name=body.get("name", ""),
            tin=body.get("tin", ""),
            vat_number=body.get("vat_number"),
            address=body.get("address", ""),
            phone=body.get("phone", ""),
            email=body.get("email", ""),
            currency_default=body.get("currency_default", "ZWG"),
        )
    else:
        for k in ("name", "tin", "vat_number", "address", "phone", "email", "currency_default"):
            if k in body:
                setattr(company, k, body[k] or ("" if k != "vat_number" else None))
    company.save()
    return JsonResponse({"success": True, "company": {"id": company.id}})


@login_required
def api_devices_list(request):
    """GET /api/devices/ - List devices."""
    if request.method == "GET":
        devices = FiscalDevice.all_objects.select_related("company").filter(is_registered=True).order_by("device_id")
        data = [
            {
                "id": d.pk,
                "device_id": d.device_id,
                "company_id": d.company_id,
                "device_serial_no": d.device_serial_no,
                "fiscal_day_status": d.fiscal_day_status,
                "last_fiscal_day_no": d.last_fiscal_day_no,
                "certificate_valid_till": d.certificate_valid_till.strftime("%Y-%m-%d") if d.certificate_valid_till else None,
            }
            for d in devices
        ]
        return JsonResponse({"devices": data})
    return JsonResponse({"error": "Use device registration page to add devices"}, status=405)


@login_required
def api_device_certificate_status(request, pk):
    """GET /api/devices/{id}/certificate-status/ - For CertificateExpiry widget."""
    try:
        device = FiscalDevice.all_objects.get(pk=pk, is_registered=True)
    except FiscalDevice.DoesNotExist:
        return JsonResponse({"error": "Device not found"}, status=404)
    tenant = getattr(request, "tenant", None)
    if tenant:
        try:
            validate_device_for_tenant(device, tenant)
        except PermissionDenied as e:
            return JsonResponse({"error": str(e)}, status=403)
    valid_till = device.certificate_valid_till
    if not valid_till:
        return JsonResponse({"expiresOn": None, "daysRemaining": None})
    from django.utils import timezone
    now = timezone.now()
    delta = valid_till - now
    days = max(0, delta.days)
    return JsonResponse({
        "expiresOn": valid_till.strftime("%Y-%m-%d"),
        "daysRemaining": days,
    })


@login_required
def api_device_detail(request, pk):
    """GET /api/devices/{id}/ - Device detail."""
    try:
        device = FiscalDevice.all_objects.get(pk=pk, is_registered=True)
    except FiscalDevice.DoesNotExist:
        return JsonResponse({"error": "Device not found"}, status=404)
    tenant = getattr(request, "tenant", None)
    if tenant:
        try:
            validate_device_for_tenant(device, tenant)
        except PermissionDenied as e:
            return JsonResponse({"error": str(e)}, status=403)
    if request.method == "GET":
        return JsonResponse({
            "device": {
                "id": device.pk,
                "device_id": device.device_id,
                "fiscal_day_status": device.fiscal_day_status,
                "last_fiscal_day_no": device.last_fiscal_day_no,
                "last_receipt_global_no": device.last_receipt_global_no,
                "certificate_valid_till": device.certificate_valid_till.strftime("%Y-%m-%d") if device.certificate_valid_till else None,
            }
        })
    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def api_device_open_day(request, pk):
    """POST /api/devices/{id}/open-day/"""
    try:
        device = FiscalDevice.all_objects.get(pk=pk, is_registered=True)
    except FiscalDevice.DoesNotExist:
        return JsonResponse({"error": "Device not found"}, status=404)
    tenant = getattr(request, "tenant", None)
    if tenant:
        try:
            validate_device_for_tenant(device, tenant)
        except PermissionDenied as e:
            return JsonResponse({"error": str(e)}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    service = DeviceApiService()
    fiscal_day, err = service.open_day(device)
    if err:
        return JsonResponse({"error": err}, status=400)
    from .services.fdms_events import emit_metrics_updated
    emit_metrics_updated()
    return JsonResponse({"success": True, "fiscal_day_no": fiscal_day.fiscal_day_no})


@login_required
def api_device_close_day(request, pk):
    """POST /api/devices/{id}/close-day/"""
    try:
        device = FiscalDevice.all_objects.get(pk=pk, is_registered=True)
    except FiscalDevice.DoesNotExist:
        return JsonResponse({"error": "Device not found"}, status=404)
    tenant = getattr(request, "tenant", None)
    if tenant:
        try:
            validate_device_for_tenant(device, tenant)
        except PermissionDenied as e:
            return JsonResponse({"error": str(e)}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    service = DeviceApiService()
    data, err = service.close_day(device)
    if err:
        return JsonResponse({"error": err}, status=400)
    from .services.fdms_events import emit_metrics_updated
    emit_metrics_updated()
    return JsonResponse({"success": True, "operation_id": data.get("operationID")})


@login_required
def api_device_ping(request, pk):
    """POST /api/devices/{id}/ping/ - Report device is online to FDMS (section 4.13)."""
    try:
        device = FiscalDevice.all_objects.get(pk=pk, is_registered=True)
    except FiscalDevice.DoesNotExist:
        return JsonResponse({"error": "Device not found"}, status=404)
    tenant = getattr(request, "tenant", None)
    if tenant:
        try:
            validate_device_for_tenant(device, tenant)
        except PermissionDenied as e:
            return JsonResponse({"error": str(e)}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    service = DeviceApiService()
    data, err = service.ping(device)
    if err:
        return JsonResponse({"error": err}, status=400)
    return JsonResponse({
        "success": True,
        "operation_id": data.get("operationID"),
        "reporting_frequency": data.get("reportingFrequency"),
    })


@login_required
def api_products_list(request):
    """GET /api/products/ - List. POST - create. Admin only."""
    if not _require_admin(request):
        return JsonResponse({"error": "Admin access required"}, status=403)
    company_id = request.GET.get("company_id")
    if request.method == "GET":
        qs = Product.objects.filter(is_active=True).select_related("company").order_by("name")
        if company_id:
            qs = qs.filter(company_id=company_id)
        data = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": str(p.price),
                "tax_code": p.tax_code,
                "tax_percent": str(p.tax_percent),
                "hs_code": p.hs_code,
                "is_active": p.is_active,
                "company_id": p.company_id,
            }
            for p in qs
        ]
        return JsonResponse({"products": data})
    body = json.loads(request.body or "{}")
    Product.objects.create(
        company_id=body.get("company_id"),
        name=body.get("name", ""),
        description=body.get("description", ""),
        price=body.get("price", 0),
        tax_code=body.get("tax_code", "VAT"),
        tax_percent=body.get("tax_percent", 15),
        hs_code=body.get("hs_code", ""),
    )
    return JsonResponse({"success": True})


@login_required
def api_product_detail(request, pk):
    """GET/PUT/DELETE /api/products/{id}/. Admin only."""
    if not _require_admin(request):
        return JsonResponse({"error": "Admin access required"}, status=403)
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)
    if request.method == "GET":
        return JsonResponse({
            "product": {
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "price": str(product.price),
                "tax_code": product.tax_code,
                "tax_percent": str(product.tax_percent),
                "hs_code": product.hs_code,
                "is_active": product.is_active,
                "company_id": product.company_id,
            }
        })
    if request.method == "PUT":
        body = json.loads(request.body or "{}")
        for k in ("name", "description", "price", "tax_code", "tax_percent", "hs_code", "is_active", "company_id"):
            if k in body:
                setattr(product, k, body[k])
        product.save()
        return JsonResponse({"success": True})
    if request.method == "DELETE":
        product.is_active = False
        product.save()
        return JsonResponse({"success": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def api_customers_list(request):
    """GET /api/customers/ - List. POST - create. Admin only."""
    if not _require_admin(request):
        return JsonResponse({"error": "Admin access required"}, status=403)
    company_id = request.GET.get("company_id")
    if request.method == "GET":
        qs = Customer.objects.filter(is_active=True).select_related("company").order_by("name")
        if company_id:
            qs = qs.filter(company_id=company_id)
        data = [
            {
                "id": c.id,
                "name": c.name,
                "tin": c.tin,
                "address": c.address,
                "phone": c.phone,
                "email": c.email,
                "is_active": c.is_active,
                "company_id": c.company_id,
            }
            for c in qs
        ]
        return JsonResponse({"customers": data})
    body = json.loads(request.body or "{}")
    Customer.objects.create(
        company_id=body.get("company_id"),
        name=body.get("name", ""),
        tin=body.get("tin", ""),
        address=body.get("address", ""),
        phone=body.get("phone", ""),
        email=body.get("email", ""),
    )
    return JsonResponse({"success": True})


@login_required
def api_customer_detail(request, pk):
    """GET/PUT/DELETE /api/customers/{id}/. Admin only."""
    if not _require_admin(request):
        return JsonResponse({"error": "Admin access required"}, status=403)
    try:
        customer = Customer.objects.get(pk=pk)
    except Customer.DoesNotExist:
        return JsonResponse({"error": "Customer not found"}, status=404)
    if request.method == "GET":
        return JsonResponse({
            "customer": {
                "id": customer.id,
                "name": customer.name,
                "tin": customer.tin,
                "address": customer.address,
                "phone": customer.phone,
                "email": customer.email,
                "is_active": customer.is_active,
                "company_id": customer.company_id,
            }
        })
    if request.method == "PUT":
        body = json.loads(request.body or "{}")
        for k in ("name", "tin", "address", "phone", "email", "is_active", "company_id"):
            if k in body:
                setattr(customer, k, body[k])
        customer.save()
        return JsonResponse({"success": True})
    if request.method == "DELETE":
        customer.is_active = False
        customer.save()
        return JsonResponse({"success": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)


# --- Tax Mappings ---


@login_required
@require_http_methods(["GET", "POST"])
def api_tax_mappings_list(request):
    """GET /api/tax-mappings/ - List. POST - Create."""
    if request.method == "GET":
        mappings = TaxMapping.objects.filter(is_active=True).order_by("sort_order", "local_code")
        return JsonResponse({
            "tax_mappings": [
                {
                    "id": m.id,
                    "local_code": m.local_code,
                    "display_name": m.display_name,
                    "fdms_tax_id": m.fdms_tax_id,
                    "fdms_tax_code": m.fdms_tax_code,
                    "tax_percent": float(m.tax_percent) if m.tax_percent is not None else None,
                    "sort_order": m.sort_order,
                }
                for m in mappings
            ]
        })
    body = json.loads(request.body or "{}")
    local_code = (body.get("local_code") or "").strip()
    fdms_tax_id = body.get("fdms_tax_id")
    fdms_tax_code = (str(body.get("fdms_tax_code", "") or "").strip()[:3]) or ""
    tax_percent = body.get("tax_percent")
    if tax_percent is not None:
        try:
            tax_percent = float(tax_percent)
        except (TypeError, ValueError):
            tax_percent = None
    if not local_code:
        return JsonResponse({"error": "local_code required"}, status=400)
    if fdms_tax_id is None:
        return JsonResponse({"error": "fdms_tax_id required"}, status=400)
    defaults = {
        "display_name": (body.get("display_name") or "").strip() or local_code,
        "fdms_tax_id": int(fdms_tax_id),
        "fdms_tax_code": fdms_tax_code,
        "sort_order": int(body.get("sort_order", 0)),
        "is_active": True,
    }
    if tax_percent is not None:
        from decimal import Decimal
        defaults["tax_percent"] = Decimal(str(round(tax_percent, 2)))
    m, _ = TaxMapping.objects.update_or_create(
        local_code=local_code.upper(),
        defaults=defaults,
    )
    return JsonResponse({"success": True, "tax_mapping": {"id": m.id}})


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_tax_mapping_detail(request, pk):
    """GET/PUT/DELETE /api/tax-mappings/<id>/"""
    try:
        m = TaxMapping.objects.get(pk=pk)
    except TaxMapping.DoesNotExist:
        return JsonResponse({"error": "Tax mapping not found"}, status=404)
    if request.method == "GET":
        return JsonResponse({
            "tax_mapping": {
                "id": m.id,
                "local_code": m.local_code,
                "display_name": m.display_name,
                "fdms_tax_id": m.fdms_tax_id,
                "fdms_tax_code": m.fdms_tax_code,
                "tax_percent": str(m.tax_percent) if m.tax_percent is not None else None,
                "sort_order": m.sort_order,
            }
        })
    if request.method == "PUT":
        body = json.loads(request.body or "{}")
        if "local_code" in body:
            m.local_code = (body["local_code"] or "").strip().upper() or m.local_code
        if "display_name" in body:
            m.display_name = (body.get("display_name") or "").strip()
        if "fdms_tax_id" in body:
            m.fdms_tax_id = int(body["fdms_tax_id"])
        if "fdms_tax_code" in body:
            m.fdms_tax_code = (str(body.get("fdms_tax_code", "") or "").strip()[:3]) or ""
        if "tax_percent" in body:
            val = body.get("tax_percent")
            if val is not None:
                try:
                    from decimal import Decimal
                    m.tax_percent = Decimal(str(round(float(val), 2)))
                except (TypeError, ValueError):
                    m.tax_percent = None
            else:
                m.tax_percent = None
        if "sort_order" in body:
            m.sort_order = int(body.get("sort_order", 0))
        m.save()
        return JsonResponse({"success": True})
    if request.method == "DELETE":
        m.is_active = False
        m.save()
        return JsonResponse({"success": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)
