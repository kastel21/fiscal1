"""
KPI metrics service for real-time dashboard.
Aggregates across all devices.
"""

from datetime import timedelta
from decimal import Decimal
from collections import defaultdict

from django.db.models import Sum, Count, Q
from django.utils import timezone

from fiscal.models import FDMSApiLog, FiscalDevice, Receipt


def get_metrics(device_id: int | None = None) -> dict:
    """
    Calculate KPI metrics for dashboard.
    If device_id is set, filter to that device; otherwise aggregate all.
    """
    now = timezone.now()
    start_24h = now - timedelta(hours=24)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    devices_qs = FiscalDevice.objects.all()
    if device_id is not None:
        devices_qs = devices_qs.filter(device_id=device_id)
    total_devices = devices_qs.count()
    active_devices = devices_qs.filter(is_registered=True).count()

    fiscal_status_dist = defaultdict(int)
    for d in devices_qs.filter(is_registered=True):
        status = d.fiscal_day_status or "Unknown"
        fiscal_status_dist[status] = fiscal_status_dist.get(status, 0) + 1

    receipts_qs = Receipt.objects.all()
    if device_id is not None:
        receipts_qs = receipts_qs.filter(device__device_id=device_id)

    receipts_today = receipts_qs.filter(
        created_at__gte=start_today,
        created_at__lte=now,
    )
    receipts_24h = receipts_qs.filter(
        created_at__gte=start_24h,
        created_at__lte=now,
    )

    fiscalised_today = receipts_today.filter(fdms_receipt_id__isnull=False).exclude(fdms_receipt_id=0)
    fiscalised_24h = receipts_24h.filter(fdms_receipt_id__isnull=False).exclude(fdms_receipt_id=0)

    failed_logs = FDMSApiLog.objects.filter(
        endpoint__icontains="SubmitReceipt",
        created_at__gte=start_24h,
        created_at__lte=now,
    ).filter(Q(status_code__isnull=True) | Q(status_code__gte=400) | Q(error_message__isnull=False))
    failed_receipts = failed_logs.count()

    total_24h = fiscalised_24h.count() + failed_receipts
    success_rate = round(100.0 * fiscalised_24h.count() / total_24h, 1) if total_24h > 0 else 100.0

    avg_latency_ms = None
    success_logs = FDMSApiLog.objects.filter(
        endpoint__icontains="SubmitReceipt",
        status_code=200,
        created_at__gte=start_24h,
    ).order_by("-created_at")[:100]
    if success_logs.exists():
        avg_latency_ms = 0

    sales_by_currency = defaultdict(Decimal)
    tax_breakdown = defaultdict(Decimal)
    for r in fiscalised_today:
        curr = r.currency or "USD"
        if r.receipt_total:
            sales_by_currency[curr] += r.receipt_total
        for t in r.receipt_taxes or []:
            pct = t.get("taxPercent") or t.get("fiscalCounterTaxPercent") or 0
            amt = t.get("taxAmount") or t.get("salesAmountWithTax") or t.get("fiscalCounterValue") or 0
            key = f"{pct}%"
            tax_breakdown[key] = tax_breakdown.get(key, Decimal("0")) + Decimal(str(amt))

    queue_depth = 0
    try:
        from offline.models import OfflineReceiptQueue
        queue_depth = OfflineReceiptQueue.objects.filter(state="QUEUED").count()
    except Exception:
        pass

    receipts_per_hour = []
    for i in range(min(24, now.hour + 1)):
        h_start = start_today + timedelta(hours=i)
        h_end = h_start + timedelta(hours=1)
        cnt = receipts_qs.filter(
            created_at__gte=h_start,
            created_at__lt=h_end,
            fdms_receipt_id__isnull=False,
        ).exclude(fdms_receipt_id=0).count()
        receipts_per_hour.append({"hour": i, "count": cnt})

    return {
        "activeDevices": active_devices,
        "totalDevices": total_devices,
        "receiptsToday": fiscalised_today.count(),
        "failedReceipts": failed_receipts,
        "successRate": success_rate,
        "avgLatencyMs": avg_latency_ms,
        "sales": {k: float(v) for k, v in sales_by_currency.items()},
        "taxBreakdown": [{"band": k, "amount": float(v)} for k, v in sorted(tax_breakdown.items(), key=lambda x: -float(x[1]))],
        "queueDepth": queue_depth,
        "fiscalStatusDistribution": dict(fiscal_status_dist),
        "receiptsPerHour": receipts_per_hour,
    }
