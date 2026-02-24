"""
Django form for Debit Note creation. Legally compliant, safe input structure.
"""

from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from fiscal.models import FiscalDevice, Receipt


class DebitNoteForm(forms.Form):
    """Form for creating a Debit Note. Must reference an invoice."""

    original_invoice_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True,
    )
    debit_reason = forms.CharField(
        required=True,
        max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Specify reason for debit"}),
    )
    debit_line_data = forms.JSONField(
        required=True,
        widget=forms.HiddenInput(),
    )

    def __init__(self, device: FiscalDevice | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._device = device

    def clean_original_invoice_id(self) -> int:
        inv_id = self.cleaned_data.get("original_invoice_id")
        if not inv_id:
            raise ValidationError("Original invoice is required.")
        try:
            orig = Receipt.objects.get(pk=inv_id)
        except Receipt.DoesNotExist:
            raise ValidationError("Original invoice not found.")
        rt = (orig.receipt_type or "").strip().upper()
        if rt not in ("FISCALINVOICE",):
            raise ValidationError("Selected document is not an invoice.")
        if not orig.fdms_receipt_id:
            raise ValidationError("Original invoice must be fiscalised.")
        doc_type = getattr(orig, "document_type", "INVOICE")
        if doc_type not in ("INVOICE", ""):
            raise ValidationError("Cannot debit a credit or debit note.")
        if self._device and orig.device_id != self._device.pk:
            raise ValidationError("Original invoice belongs to a different device.")
        self._original_receipt = orig
        return inv_id

    def clean_debit_reason(self) -> str:
        reason = (self.cleaned_data.get("debit_reason") or "").strip()
        if not reason:
            raise ValidationError("Debit reason is required.")
        return reason[:500]

    def clean_debit_line_data(self) -> list[dict]:
        data = self.cleaned_data.get("debit_line_data")
        if not isinstance(data, list):
            raise ValidationError("Invalid line data.")
        return data

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if self.errors:
            return cleaned

        original = getattr(self, "_original_receipt", None)
        if not original:
            return cleaned

        line_data = cleaned.get("debit_line_data") or []
        debit_total = Decimal("0")

        for row in line_data:
            if not isinstance(row, dict):
                continue
            amt = row.get("amount") or row.get("line_total") or 0
            try:
                debit_total += Decimal(str(amt))
            except (TypeError, ValueError):
                pass

        if debit_total <= 0:
            self.add_error(
                "debit_line_data",
                ValidationError("Debit amount must be greater than zero."),
            )
            return cleaned

        cleaned["_debit_total"] = debit_total
        cleaned["_debit_lines"] = self._build_debit_lines(line_data)
        return cleaned

    def _build_debit_lines(self, line_data: list[dict]) -> list[dict]:
        lines: list[dict] = []
        for i, row in enumerate(line_data):
            if not isinstance(row, dict):
                continue
            desc = str(row.get("description", row.get("receiptLineName", "")))[:200] or "Additional charge"
            amt = row.get("amount") or row.get("line_total") or 0
            try:
                amt_dec = Decimal(str(amt))
            except (TypeError, ValueError):
                continue
            if amt_dec <= 0:
                continue
            lines.append({
                "description": desc,
                "line_total": float(amt_dec),
                "quantity": 1,
                "row_num": i + 1,
            })
        return lines
