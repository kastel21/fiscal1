"""
Celery tasks for FDMS fiscal engine.

Tasks: submit_receipt_task, open_day_task, close_day_task, ping_devices_task,
run_fdms_ping (multi-tenant), ping_single_tenant.
Each task logs ActivityEvent, AuditEvent, and emits WebSocket events.
"""

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import connection

from fiscal.models import FiscalDevice
from fiscal.services.ping_service import send_ping
from fiscal.services.activity_audit import log_activity, log_audit
from fiscal.services.device_api import DeviceApiService
from fiscal.services.fdms_events import emit_metrics_updated, emit_to_device
from fiscal.services.receipt_service import submit_receipt

logger = logging.getLogger("fiscal")


def _emit_progress(device_id: int, percent: int, stage: str, invoice_no: str = "") -> None:
    """Emit receipt.progress WebSocket event."""
    emit_to_device(
        device_id,
        "receipt.progress",
        {"percent": percent, "stage": stage, "invoice_no": invoice_no},
    )


@shared_task(bind=True, name="fiscal.submit_receipt_task")
def submit_receipt_task(
    self,
    device_id: int,
    fiscal_day_no: int,
    receipt_type: str,
    receipt_currency: str,
    invoice_no: str,
    receipt_lines: list[dict],
    receipt_taxes: list[dict],
    receipt_payments: list[dict],
    receipt_total: float,
    receipt_lines_tax_inclusive: bool = True,
    original_invoice_no: str = "",
    original_receipt_global_no: int | None = None,
) -> dict[str, Any]:
    """
    Submit receipt to FDMS via Celery. Emits progress events and logs activity/audit.
    Returns {"success": True, "receipt_global_no": N, "fdms_receipt_id": X} or {"success": False, "error": str}.
    """
    try:
        device = FiscalDevice.objects.get(device_id=device_id)
    except FiscalDevice.DoesNotExist:
        emit_to_device(device_id, "error", {"message": f"Device {device_id} not found"})
        return {"success": False, "error": "Device not found"}

    def progress_emit(percent: int, stage: str) -> None:
        _emit_progress(device_id, percent, stage, invoice_no)

    log_activity(device, "receipt_submit_started", f"Submitting receipt {invoice_no}", "info")
    log_audit(device, "receipt_submit_started", {"invoice_no": invoice_no, "fiscal_day_no": fiscal_day_no})

    receipt_date = None
    try:
        receipt_obj, err = submit_receipt(
            device=device,
            fiscal_day_no=fiscal_day_no,
            receipt_type=receipt_type,
            receipt_currency=receipt_currency,
            invoice_no=invoice_no,
            receipt_lines=receipt_lines,
            receipt_taxes=receipt_taxes,
            receipt_payments=receipt_payments,
            receipt_total=receipt_total,
            receipt_lines_tax_inclusive=receipt_lines_tax_inclusive,
            receipt_date=receipt_date,
            original_invoice_no=original_invoice_no,
            original_receipt_global_no=original_receipt_global_no,
            progress_emit=progress_emit,
        )
    except Exception as e:
        logger.exception("submit_receipt_task failed")
        emit_to_device(device_id, "error", {"message": str(e)})
        log_activity(device, "receipt_submit_failed", str(e), "error")
        log_audit(device, "receipt_submit_failed", {"invoice_no": invoice_no, "error": str(e)})
        emit_metrics_updated()
        return {"success": False, "error": str(e)}

    if err:
        emit_to_device(device_id, "error", {"message": err})
        log_activity(device, "receipt_submit_failed", err, "error")
        log_audit(device, "receipt_submit_failed", {"invoice_no": invoice_no, "error": err})
        emit_metrics_updated()
        return {"success": False, "error": err}

    emit_to_device(
        device_id,
        "receipt.completed",
        {
            "receipt_global_no": receipt_obj.receipt_global_no,
            "fdms_receipt_id": receipt_obj.fdms_receipt_id,
            "invoice_no": invoice_no,
        },
    )
    log_activity(
        device,
        "receipt_submitted",
        f"Receipt {invoice_no} fiscalized (global #{receipt_obj.receipt_global_no})",
        "info",
    )
    log_audit(
        device,
        "receipt_submitted",
        {"invoice_no": invoice_no, "receipt_global_no": receipt_obj.receipt_global_no, "fdms_receipt_id": receipt_obj.fdms_receipt_id},
    )
    emit_metrics_updated()
    return {
        "success": True,
        "receipt_global_no": receipt_obj.receipt_global_no,
        "fdms_receipt_id": receipt_obj.fdms_receipt_id,
    }


@shared_task(bind=True, name="fiscal.open_day_task")
def open_day_task(self, device_id: int) -> dict[str, Any]:
    """
    Open fiscal day via Celery. Emits fiscal.opened and logs activity/audit.
    Returns {"success": True, "fiscal_day_no": N} or {"success": False, "error": str}.
    """
    try:
        device = FiscalDevice.objects.get(device_id=device_id)
    except FiscalDevice.DoesNotExist:
        emit_to_device(device_id, "error", {"message": f"Device {device_id} not found"})
        return {"success": False, "error": "Device not found"}

    log_activity(device, "fiscal_open_started", "Opening fiscal day", "info")
    log_audit(device, "fiscal_day_open_started", {})

    service = DeviceApiService()
    fiscal_day, err = service.open_day(device)

    if err:
        emit_to_device(device_id, "error", {"message": err})
        log_activity(device, "fiscal_open_failed", err, "error")
        log_audit(device, "fiscal_day_open_failed", {"error": err})
        return {"success": False, "error": err}

    emit_to_device(
        device_id,
        "fiscal.opened",
        {"fiscal_day_no": fiscal_day.fiscal_day_no, "status": "FiscalDayOpened"},
    )
    log_activity(device, "fiscal_day_opened", f"Fiscal day #{fiscal_day.fiscal_day_no} opened", "info")
    log_audit(device, "fiscal_day_opened", {"fiscal_day_no": fiscal_day.fiscal_day_no})
    emit_metrics_updated()
    return {"success": True, "fiscal_day_no": fiscal_day.fiscal_day_no}


@shared_task(bind=True, name="fiscal.close_day_task")
def close_day_task(self, device_id: int) -> dict[str, Any]:
    """
    Close fiscal day via Celery. Emits fiscal.closed and logs activity/audit.
    Returns {"success": True, "operation_id": X} or {"success": False, "error": str}.
    Note: CloseDay initiates async; call poll_until_closed separately or poll via status.
    """
    try:
        device = FiscalDevice.objects.get(device_id=device_id)
    except FiscalDevice.DoesNotExist:
        emit_to_device(device_id, "error", {"message": f"Device {device_id} not found"})
        return {"success": False, "error": "Device not found"}

    log_activity(device, "fiscal_close_started", "Closing fiscal day", "info")
    log_audit(device, "fiscal_day_close_started", {})

    service = DeviceApiService()
    data, err = service.close_day(device)

    if err:
        emit_to_device(device_id, "error", {"message": err})
        log_activity(device, "fiscal_close_failed", err, "error")
        log_audit(device, "fiscal_day_close_failed", {"error": err})
        return {"success": False, "error": err}

    operation_id = data.get("operationID", "")
    emit_to_device(
        device_id,
        "fiscal.closed",
        {"operation_id": operation_id, "status": "FiscalDayCloseInitiated"},
    )
    log_activity(device, "fiscal_day_close_initiated", f"Close initiated (op {operation_id})", "info")
    log_audit(device, "fiscal_day_close_initiated", {"operation_id": operation_id})
    emit_metrics_updated()
    return {"success": True, "operation_id": operation_id}


@shared_task(name="fiscal.ping_devices_task")
def ping_devices_task() -> dict[str, Any]:
    """
    Ping FDMS for each registered device (report device online). Runs automatically every 5 minutes via Celery Beat.
    Returns {"poked": N, "errors": [{device_id, error}, ...]}.
    """
    devices = list(FiscalDevice.objects.filter(is_registered=True))
    if not devices:
        return {"poked": 0, "errors": []}

    service = DeviceApiService()
    poked = 0
    errors: list[dict[str, Any]] = []

    for device in devices:
        data, err = service.ping(device)
        if err:
            errors.append({"device_id": device.device_id, "error": err})
            logger.warning("Ping failed for device %s: %s", device.device_id, err)
        else:
            poked += 1

    if poked or errors:
        emit_metrics_updated()
    return {"poked": poked, "errors": errors}


FDMS_PING_LOCK_KEY = "fdms:ping:run_fdms_ping"
FDMS_PING_LOCK_EXPIRE_SECONDS = 300


def _acquire_ping_lock():
    """Acquire Redis lock for run_fdms_ping to prevent overlapping execution. Returns True if acquired."""
    try:
        import redis
        broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
        r = redis.from_url(broker_url)
        acquired = r.set(FDMS_PING_LOCK_KEY, "1", nx=True, ex=FDMS_PING_LOCK_EXPIRE_SECONDS)
        return bool(acquired)
    except Exception as e:
        logger.warning("FDMS ping lock acquire failed: %s", e)
        return False


@shared_task(name="fiscal.run_fdms_ping", bind=True)
def run_fdms_ping(self) -> dict[str, Any]:
    """
    Multi-tenant FDMS Ping: enqueue ping_single_tenant for each active tenant.
    Runs every 5 minutes via django-celery-beat. Uses Redis lock to prevent overlap.
    Returns {"scheduled": N, "skipped_lock": bool, "errors": [...]}.
    """
    if not _acquire_ping_lock():
        logger.info("FDMS ping skipped: previous run still active (lock held)")
        return {"scheduled": 0, "skipped_lock": True, "errors": []}
    try:
        from tenants.models import Tenant
        tenants = list(Tenant.objects.filter(is_active=True).values_list("pk", flat=True))
    except Exception as e:
        logger.exception("FDMS ping failed to load tenants")
        return {"scheduled": 0, "skipped_lock": False, "errors": [str(e)]}
    finally:
        connection.close()

    scheduled = 0
    for tenant_id in tenants:
        try:
            ping_single_tenant.delay(str(tenant_id))
            scheduled += 1
        except Exception as e:
            logger.warning(
                "FDMS ping enqueue failed for tenant %s: %s",
                tenant_id,
                e,
                extra={"tenant_id": str(tenant_id)},
            )
    logger.info(
        "FDMS ping scheduled for %d tenant(s)",
        scheduled,
        extra={"scheduled": scheduled, "total_tenants": len(tenants)},
    )
    return {"scheduled": scheduled, "skipped_lock": False, "errors": []}


@shared_task(name="fiscal.ping_single_tenant", bind=True)
def ping_single_tenant(self, tenant_id: str) -> dict[str, Any]:
    """
    Send FDMS Ping for one tenant. Loads tenant, resolves device, calls send_ping(tenant).
    Never raises; returns {"success": bool, "tenant_slug": str, "device_id": int?, "error": str?}.
    """
    from tenants.models import Tenant
    try:
        tenant = Tenant.objects.get(pk=tenant_id)
    except Tenant.DoesNotExist:
        logger.warning("FDMS ping tenant not found", extra={"tenant_id": tenant_id})
        return {"success": False, "tenant_id": tenant_id, "tenant_slug": "", "device_id": None, "error": "Tenant not found"}
    except Exception as e:
        logger.exception("FDMS ping failed to load tenant %s", tenant_id)
        return {"success": False, "tenant_id": tenant_id, "tenant_slug": "", "device_id": None, "error": str(e)}
    finally:
        connection.close()

    try:
        data, err = send_ping(tenant)
        if err:
            logger.warning(
                "FDMS ping failed",
                extra={
                    "tenant_id": str(tenant.pk),
                    "tenant_slug": tenant.slug,
                    "tenant_name": tenant.name,
                    "device_id": tenant.device_id,
                    "success": False,
                    "error": err,
                },
            )
            return {"success": False, "tenant_id": str(tenant.pk), "tenant_slug": tenant.slug, "device_id": tenant.device_id, "error": err}
        status = "ok"
        if data:
            reporting_freq = data.get("reportingFrequency")
            operation_id = data.get("operationID") or data.get("operationId")
            logger.info(
                "FDMS ping success",
                extra={
                    "tenant_id": str(tenant.pk),
                    "tenant_slug": tenant.slug,
                    "tenant_name": tenant.name,
                    "device_id": tenant.device_id,
                    "success": True,
                    "status": status,
                    "reporting_frequency": reporting_freq,
                    "operation_id": operation_id,
                },
            )
        else:
            logger.info(
                "FDMS ping success",
                extra={
                    "tenant_id": str(tenant.pk),
                    "tenant_slug": tenant.slug,
                    "tenant_name": tenant.name,
                    "device_id": tenant.device_id,
                    "success": True,
                    "status": status,
                },
            )
        emit_metrics_updated()
        return {"success": True, "tenant_id": str(tenant.pk), "tenant_slug": tenant.slug, "device_id": tenant.device_id, "error": None}
    except Exception as e:
        logger.exception(
            "FDMS ping exception for tenant %s",
            tenant.slug,
            extra={
                "tenant_id": str(tenant.pk),
                "tenant_slug": tenant.slug,
                "device_id": tenant.device_id,
            },
        )
        return {"success": False, "tenant_id": str(tenant.pk), "tenant_slug": tenant.slug, "device_id": tenant.device_id, "error": str(e)}
    finally:
        connection.close()


@shared_task(name="fiscal.fiscalise_receipt_task")
def fiscalise_receipt_task(receipt_id: int) -> None:
    """
    Async fiscalisation for a receipt (e.g. QB webhook-created PENDING receipt).
    Calls fiscal.services.fiscal_service.fiscalise_receipt(receipt_id).
    """
    from fiscal.services.fiscal_service import fiscalise_receipt
    fiscalise_receipt(receipt_id)
