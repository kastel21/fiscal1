"""
Dashboard aggregation service. FDMS-confirmed data only.
Read-only, immutable, audit-safe.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.utils import timezone

from fiscal.models import FDMSApiLog, FiscalDay, FiscalDevice, Receipt


def _date_range(range_key: str):
    """Return (start, end) datetime for range. Uses UTC."""
    now = timezone.now()
    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "week":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "month":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    # default today
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def get_summary(device_id: int | None, range_key: str = "today", tenant=None) -> dict:
    """
    Aggregates FDMS-confirmed metrics only. Drafts never affect totals.
    When tenant is provided, device and all queries are scoped to that tenant.
    """
    device = None
    base_qs = FiscalDevice.all_objects.filter(is_registered=True)
    if tenant is not None:
        base_qs = base_qs.filter(tenant=tenant)
    if device_id:
        device = base_qs.filter(device_id=device_id).first()
    if not device:
        device = base_qs.order_by("device_id").first()
    if not device:
        return {
            "status": {"fiscalDay": "N/A", "fdmsConnectivity": "N/A", "certificate": "N/A", "lastSync": None},
            "metrics": {"invoicesFiscalised": 0, "creditNotes": 0, "netTotal": 0, "vatTotal": 0},
            "pipeline": {"draft": 0, "pending": 0, "fiscalised": 0, "failed": 0},
            "compliance": {},
        }

    start_dt, end_dt = _date_range(range_key)
    receipts = Receipt.all_objects.filter(device=device, created_at__gte=start_dt, created_at__lte=end_dt)

    fiscalised = receipts.filter(fdms_receipt_id__isnull=False).exclude(fdms_receipt_id=0)
    draft_receipts = receipts.filter(Q(fdms_receipt_id__isnull=True) | Q(fdms_receipt_id=0))
    invoices = fiscalised.filter(receipt_type="FiscalInvoice")
    credit_notes = fiscalised.filter(receipt_type="CreditNote")

    net_result = fiscalised.aggregate(s=Sum("receipt_total"))
    net_total = net_result["s"] or Decimal("0")

    vat_total = Decimal("0")
    for r in fiscalised:
        for t in r.receipt_taxes or []:
            amt = t.get("taxAmount") or t.get("fiscalCounterValue") or 0
            vat_total += Decimal(str(amt))

    log_base = FDMSApiLog.all_objects.filter(created_at__gte=start_dt, created_at__lte=end_dt)
    if tenant is not None:
        log_base = log_base.filter(tenant=tenant)
    submit_failures = log_base.filter(
        endpoint__icontains="SubmitReceipt",
    ).filter(Q(status_code__isnull=True) | Q(status_code__gte=400) | Q(error_message__isnull=False))
    failed_count = submit_failures.count()

    last_open = log_base.filter(endpoint__icontains="OpenDay").order_by("-created_at").first()
    last_close = log_base.filter(endpoint__icontains="CloseDay").order_by("-created_at").first()
    last_ping = log_base.filter(endpoint__icontains="Ping").order_by("-created_at").first()
    reporting_frequency = None
    if last_ping and last_ping.status_code == 200 and last_ping.response_payload:
        reporting_frequency = last_ping.response_payload.get("reportingFrequency")

    cert_status = "VALID"
    if device.certificate_valid_till:
        days_left = (device.certificate_valid_till - timezone.now()).days
        if days_left < 0:
            cert_status = f"EXPIRED ({abs(days_left)} days ago)"
        elif days_left < 14:
            cert_status = f"EXPIRING ({days_left} days)"

    fdms_ok = device.fiscal_day_status not in (None, "")
    last_log_qs = FDMSApiLog.all_objects.order_by("-created_at")
    if tenant is not None:
        last_log_qs = last_log_qs.filter(tenant=tenant)
    last_log = last_log_qs.first()
    last_sync = last_log.created_at.isoformat() if last_log and last_log.created_at else None

    return {
        "status": {
            "fiscalDay": "OPEN" if device.fiscal_day_status == "FiscalDayOpened" else "CLOSED",
            "fdmsConnectivity": "OK" if fdms_ok else "ERROR",
            "certificate": cert_status,
            "lastSync": last_sync,
        },
        "metrics": {
            "invoicesFiscalised": invoices.count(),
            "creditNotes": credit_notes.count(),
            "netTotal": float(net_total),
            "vatTotal": float(vat_total),
        },
        "pipeline": {
            "draft": draft_receipts.count(),
            "pending": 0,  # No async workflow; pending = 0
            "fiscalised": fiscalised.count(),
            "failed": failed_count,
        },
        "compliance": {
            "lastOpenDay": last_open.created_at.isoformat() if last_open and last_open.created_at else None,
            "lastCloseDay": last_close.created_at.isoformat() if last_close and last_close.created_at else None,
            "lastPing": last_ping.created_at.isoformat() if last_ping and last_ping.created_at else None,
            "reportingFrequency": reporting_frequency,
            "lastReceiptGlobalNo": device.last_receipt_global_no,
            "outstandingRisks": [],
        },
        "alerts": _get_alerts(device, cert_status, failed_count),
    }


def _get_alerts(device: FiscalDevice, cert_status: str, failed_count: int) -> list:
    """Build in-app alert list."""
    alerts = []
    if cert_status == "EXPIRED":
        alerts.append({"severity": "CRITICAL", "message": "Certificate expired – submissions blocked", "deviceId": device.device_id})
    elif cert_status == "EXPIRING":
        alerts.append({"severity": "WARNING", "message": "Certificate expiring within 14 days", "deviceId": device.device_id})
    if device.fiscal_day_status == "FiscalDayCloseFailed":
        alerts.append({"severity": "CRITICAL", "message": "CloseDay failure", "deviceId": device.device_id})
    if failed_count > 0:
        alerts.append({"severity": "WARNING", "message": f"{failed_count} failed receipt(s) in period", "deviceId": device.device_id})
    return alerts


def get_errors(device_id: int | None, range_key: str = "today", tenant=None) -> list:
    """Recent FDMS errors with operationID for linking and retry. Tenant-scoped when tenant is provided."""
    start_dt, end_dt = _date_range(range_key)
    qs = FDMSApiLog.all_objects.filter(
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).filter(Q(status_code__gte=400) | Q(status_code__isnull=True) | Q(error_message__isnull=False))
    qs = qs.exclude(error_message="")
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    if device_id:
        qs = qs.filter(endpoint__icontains=f"/{device_id}/")
    qs = qs.order_by("-created_at")[:50]
    return [
        {
            "id": log.pk,
            "endpoint": log.endpoint,
            "statusCode": log.status_code,
            "error": log.error_message or f"HTTP {log.status_code}",
            "operationId": log.operation_id or None,
            "createdAt": log.created_at.isoformat(),
        }
        for log in qs
    ]


def get_receipts(device_id: int | None, range_key: str = "today", status_filter: str | None = None, tenant=None) -> list:
    """Receipt pipeline list for dashboard. Optional status_filter: draft|fiscalised|failed. Tenant-scoped when tenant is provided."""
    device = None
    base_qs = FiscalDevice.all_objects.filter(is_registered=True)
    if tenant is not None:
        base_qs = base_qs.filter(tenant=tenant)
    if device_id:
        device = base_qs.filter(device_id=device_id).first()
    if not device:
        device = base_qs.order_by("device_id").first()
    if not device:
        return []
    start_dt, end_dt = _date_range(range_key)
    qs = Receipt.all_objects.filter(device=device, created_at__gte=start_dt, created_at__lte=end_dt)
    if status_filter == "draft":
        qs = qs.filter(Q(fdms_receipt_id__isnull=True) | Q(fdms_receipt_id=0))
    elif status_filter == "fiscalised":
        qs = qs.filter(fdms_receipt_id__isnull=False).exclude(fdms_receipt_id=0)
    receipts = qs.order_by("-created_at")[:100]
    return [
        {
            "id": r.pk,
            "receiptGlobalNo": r.receipt_global_no,
            "fiscalDayNo": r.fiscal_day_no,
            "receiptType": r.receipt_type,
            "total": float(r.receipt_total or 0),
            "fdmsReceiptId": r.fdms_receipt_id,
            "status": "fiscalised" if (r.fdms_receipt_id and r.fdms_receipt_id != 0) else "draft",
            "createdAt": r.created_at.isoformat(),
        }
        for r in receipts
    ]


def get_quickbooks_stub(tenant=None) -> dict:
    """QuickBooks integration status for dashboard. Tenant-scoped: connection and invoices filtered by tenant."""
    from fiscal.models import QuickBooksConnection, QuickBooksInvoice
    conn = None
    qs = QuickBooksInvoice.objects.none()
    if tenant is not None:
        conn = QuickBooksConnection.objects.filter(tenant=tenant, is_active=True).first()
        qs = QuickBooksInvoice.objects.filter(tenant=tenant).order_by("-created_at")[:500]
    fiscalised = qs.filter(fiscalised=True).count()
    pending = qs.filter(fiscalised=False).count()
    last_event = None
    try:
        from fiscal.models import QuickBooksEvent
        ev = QuickBooksEvent.objects.order_by("-created_at").first()
        last_event = ev.created_at.isoformat() if ev and ev.created_at else None
    except Exception:
        pass
    return {
        "connected": bool(conn and conn.access_token_encrypted),
        "realmId": conn.realm_id if conn else None,
        "invoicesReceived": qs.count(),
        "fiscalised": fiscalised,
        "pending": pending,
        "failed": sum(1 for inv in qs if not inv.fiscalised and (inv.fiscal_error or "").strip()),
        "lastWebhookTime": last_event,
    }
