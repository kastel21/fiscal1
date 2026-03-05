"""
Invoice number generation: INV-yyyy-N, CN-yyyy-N, DB-yyyy-N with auto-increment per year.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from fiscal.models import (
    DocumentSequence,
    DocumentSequenceAdjustment,
    InvoiceSequence,
)

_PREFIX_BY_TYPE = {
    "INVOICE": "INV",
    "CREDIT_NOTE": "CN",
    "DEBIT_NOTE": "DB",
}

_MAX_SEQUENCE_RETRIES = 5
_ALLOWED_DOCUMENT_TYPES = {"INVOICE", "CREDIT_NOTE", "DEBIT_NOTE"}


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


def adjust_document_sequence(
    document_type: str,
    year: int,
    *,
    set_next: int | None = None,
    skip_by: int | None = None,
    reason: str,
    user=None,
) -> dict:
    """
    Manually adjust sequence for INVOICE/CREDIT_NOTE/DEBIT_NOTE.
    Uses row lock + transaction and writes an audit row.
    """
    if document_type not in _ALLOWED_DOCUMENT_TYPES:
        raise ValidationError("Invalid document_type.")
    if bool(set_next is not None) == bool(skip_by is not None):
        raise ValidationError("Provide exactly one of set_next or skip_by.")
    if not isinstance(year, int) or year < 2000 or year > 9999:
        raise ValidationError("Year must be a valid 4-digit integer.")
    if not (reason and str(reason).strip()):
        raise ValidationError("Reason is required.")
    reason_clean = str(reason).strip()

    if set_next is not None:
        if int(set_next) <= 0:
            raise ValidationError("set_next must be greater than zero.")
        mode = "set_next"
        value = int(set_next)
    else:
        if int(skip_by) <= 0:
            raise ValidationError("skip_by must be greater than zero.")
        mode = "skip_by"
        value = int(skip_by)

    with transaction.atomic():
        if document_type == "INVOICE":
            seq = (
                InvoiceSequence.objects.select_for_update()
                .filter(year=year)
                .order_by("id")
                .first()
            )
            if not seq:
                seq = InvoiceSequence.objects.create(year=year, last_number=0)
            old_last_number = int(seq.last_number or 0)
        else:
            seq = (
                DocumentSequence.objects.select_for_update()
                .filter(year=year, document_type=document_type)
                .order_by("id")
                .first()
            )
            if not seq:
                seq = DocumentSequence.objects.create(
                    year=year, document_type=document_type, last_number=0
                )
            old_last_number = int(seq.last_number or 0)

        if mode == "set_next":
            new_last_number = value - 1
            if new_last_number < old_last_number:
                raise ValidationError(
                    "Cannot move sequence backwards without explicit override."
                )
        else:
            new_last_number = old_last_number + value

        seq.last_number = new_last_number
        seq.save(update_fields=["last_number"])

        next_number_preview = f"{_PREFIX_BY_TYPE[document_type]}-{year}-{new_last_number + 1}"

        DocumentSequenceAdjustment.objects.create(
            tenant=getattr(seq, "tenant", None),
            document_type=document_type,
            year=year,
            mode=mode,
            value=value,
            old_last_number=old_last_number,
            new_last_number=new_last_number,
            reason=reason_clean,
            changed_by=user if getattr(user, "is_authenticated", False) else None,
        )

    return {
        "document_type": document_type,
        "year": year,
        "mode": mode,
        "value": value,
        "old_last_number": old_last_number,
        "new_last_number": new_last_number,
        "next_number_preview": next_number_preview,
    }
