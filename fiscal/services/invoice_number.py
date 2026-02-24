"""
Invoice number generation: INV-yyyy-N, CN-yyyy-N, DB-yyyy-N with auto-increment per year.
"""

from django.db import transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from fiscal.models import DocumentSequence, InvoiceSequence

_PREFIX_BY_TYPE = {
    "INVOICE": "INV",
    "CREDIT_NOTE": "CN",
    "DEBIT_NOTE": "DB",
}

_MAX_SEQUENCE_RETRIES = 5


def get_next_invoice_no() -> str:
    """
    Return next invoice number in format INV-yyyy-N.
    Atomic per-year sequence. Thread-safe; retries on concurrent create (IntegrityError).
    """
    year = timezone.now().year
    for _ in range(_MAX_SEQUENCE_RETRIES):
        with transaction.atomic():
            seq = InvoiceSequence.objects.select_for_update().filter(year=year).first()
            if seq:
                seq.last_number += 1
                seq.save(update_fields=["last_number"])
                return f"INV-{year}-{seq.last_number}"
            try:
                InvoiceSequence.objects.create(year=year, last_number=1)
                return f"INV-{year}-1"
            except IntegrityError:
                # Another process created the row; retry to lock and increment
                pass
    raise RuntimeError("get_next_invoice_no: too many retries (concurrent contention)")


def get_next_credit_note_no() -> str:
    """Return next credit note number in format CN-yyyy-N. Thread-safe."""
    return _get_next_document_no("CREDIT_NOTE")


def get_next_debit_note_no() -> str:
    """Return next debit note number in format DB-yyyy-N. Thread-safe."""
    return _get_next_document_no("DEBIT_NOTE")


def _get_next_document_no(document_type: str) -> str:
    year = timezone.now().year
    prefix = _PREFIX_BY_TYPE.get(document_type, document_type[:2].upper())
    for _ in range(_MAX_SEQUENCE_RETRIES):
        with transaction.atomic():
            seq = DocumentSequence.objects.select_for_update().filter(
                year=year, document_type=document_type
            ).first()
            if seq:
                seq.last_number += 1
                seq.save(update_fields=["last_number"])
                return f"{prefix}-{year}-{seq.last_number}"
            try:
                DocumentSequence.objects.create(
                    year=year, document_type=document_type, last_number=1
                )
                return f"{prefix}-{year}-1"
            except IntegrityError:
                pass
    raise RuntimeError(
        f"_get_next_document_no({document_type}): too many retries (concurrent contention)"
    )


def generate_document_number(document_type: str, sequence: int) -> str:
    """
    Format document number from type and sequence. Does not advance sequence.
    INVOICE -> INV-, CREDIT_NOTE -> CN-, DEBIT_NOTE -> DB-.
    """
    year = timezone.now().year
    prefix = _PREFIX_BY_TYPE.get(document_type, "INV")
    return f"{prefix}-{year}-{sequence}"
