"""
Celery tasks for QuickBooks webhook processing.
Process invoice webhooks: fetch from QB, idempotency check, fiscalise via FDMS, update QB, mark processed.
"""

import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="quickbooks.process_qb_invoice_webhook", bind=True, max_retries=3)
def process_qb_invoice_webhook(self, realm_id: str, invoice_id: str):
    """
    Process a QuickBooks Invoice webhook event: fetch invoice, check idempotency,
    fiscalise if not already done, update QuickBooks with receipt info, mark event processed.
    Idempotent and safe to retry.
    """
    realm_id = str(realm_id or "").strip()
    invoice_id = str(invoice_id or "").strip()
    if not realm_id or not invoice_id:
        logger.warning(
            "process_qb_invoice_webhook skipped: missing realm_id or invoice_id",
            extra={"realm_id": realm_id, "invoice_id": invoice_id},
        )
        return

    from quickbooks.models import QuickBooksWebhookEvent

    # Mark as processed only at the end; we may run multiple times (retries) so idempotency is key
    events = list(
        QuickBooksWebhookEvent.objects.filter(
            realm_id=realm_id,
            entity_name="Invoice",
            entity_id=invoice_id,
            processed=False,
        ).order_by("created_at")
    )

    # Idempotency: already have a fiscal record for this invoice?
    try:
        from fiscal.models import QuickBooksInvoice
        existing = QuickBooksInvoice.objects.filter(qb_invoice_id=invoice_id).first()
        if existing and existing.fiscalised and existing.fiscal_receipt_id:
            logger.info(
                "QuickBooks invoice already fiscalised; skipping",
                extra={"realm_id": realm_id, "invoice_id": invoice_id, "processing_result": "skipped_already_fiscalised"},
            )
            QuickBooksWebhookEvent.objects.filter(
                realm_id=realm_id, entity_name="Invoice", entity_id=invoice_id, processed=False
            ).update(processed=True)
            return
    except Exception as e:
        logger.warning("Idempotency check failed (fiscal app): %s", e, extra={"realm_id": realm_id, "invoice_id": invoice_id})

    # Fetch full invoice from QuickBooks
    payload = None
    try:
        from fiscal.services.qb_service import fetch_invoice_from_qb
        payload = fetch_invoice_from_qb(invoice_id, realm_id, entity_name="Invoice")
    except Exception as e:
        logger.exception(
            "Fetch invoice from QuickBooks failed: %s",
            e,
            extra={"realm_id": realm_id, "invoice_id": invoice_id, "processing_result": "fetch_error"},
        )
        raise self.retry(exc=e)

    if not payload:
        logger.warning(
            "Could not fetch QuickBooks invoice; will not fiscalise",
            extra={"realm_id": realm_id, "invoice_id": invoice_id, "processing_result": "fetch_empty"},
        )
        QuickBooksWebhookEvent.objects.filter(
            realm_id=realm_id, entity_name="Invoice", entity_id=invoice_id, processed=False
        ).update(processed=True)
        return

    # Idempotency: invoice already has fiscal receipt number in PrivateNote?
    private_note = (payload.get("PrivateNote") or "").strip()
    if private_note and ("Fiscalised" in private_note or "receipt" in private_note.lower() or "GlobalNo" in private_note):
        logger.info(
            "QuickBooks invoice already has fiscal note; skipping",
            extra={"realm_id": realm_id, "invoice_id": invoice_id, "processing_result": "skipped_has_note"},
        )
        QuickBooksWebhookEvent.objects.filter(
            realm_id=realm_id, entity_name="Invoice", entity_id=invoice_id, processed=False
        ).update(processed=True)
        return

    # Fiscalise via existing FDMS flow (do not duplicate logic)
    try:
        from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice
        qb_inv, err = fiscalise_qb_invoice(invoice_id, payload)
    except Exception as e:
        logger.exception(
            "Fiscalise QB invoice failed: %s",
            e,
            extra={"realm_id": realm_id, "invoice_id": invoice_id, "processing_result": "fiscalise_error"},
        )
        raise self.retry(exc=e)

    if not qb_inv:
        logger.warning(
            "fiscalise_qb_invoice returned no invoice: %s",
            err,
            extra={"realm_id": realm_id, "invoice_id": invoice_id, "processing_result": "fiscalise_failed"},
        )
        QuickBooksWebhookEvent.objects.filter(
            realm_id=realm_id, entity_name="Invoice", entity_id=invoice_id, processed=False
        ).update(processed=True)
        return

    if qb_inv.fiscalised and qb_inv.fiscal_receipt_id:
        # Optionally push PrivateNote back to QuickBooks (update invoice)
        try:
            receipt = qb_inv.fiscal_receipt
            sync_token = str((payload.get("SyncToken") or "0"))
            private_note = f"Fiscalised via FDMS. Receipt No: {receipt.receipt_global_no or receipt.fdms_receipt_id or 'N/A'}"
            from quickbooks.services import push_invoice_update
            push_invoice_update(realm_id, invoice_id, sync_token, private_note=private_note, user=None)
        except Exception as e:
            logger.warning(
                "Update QuickBooks invoice (PrivateNote) failed: %s",
                e,
                extra={"realm_id": realm_id, "invoice_id": invoice_id},
            )

    QuickBooksWebhookEvent.objects.filter(
        realm_id=realm_id, entity_name="Invoice", entity_id=invoice_id, processed=False
    ).update(processed=True)

    logger.info(
        "QuickBooks webhook processed",
        extra={
            "realm_id": realm_id,
            "invoice_id": invoice_id,
            "processing_result": "fiscalised" if (qb_inv and qb_inv.fiscalised) else "pending_or_failed",
            "fiscalised": bool(qb_inv and qb_inv.fiscalised),
        },
    )
