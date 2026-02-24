"""
Django form for Credit Note creation. Legally compliant, safe input structure.
"""

from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from fiscal.models import FiscalDevice, Receipt


CREDIT_REASONS = [
    ("RETURNED_GOODS", "Returned goods"),
    ("PRICING_ERROR", "Pricing error"),
    ("POST_SALE_DISCOUNT", "Post-sale discount"),
    ("DAMAGED_GOODS", "Damaged goods"),
    ("OTHER", "Other"),
]

REFUND_METHODS = [
    ("CASH", "CASH"),
    ("CARD", "CARD"),
    ("BANK_TRANSFER", "BANK_TRANSFER"),
    ("OFFSET", "OFFSET (apply to customer balance)"),
]


class CreditNoteForm(forms.Form):
    """Form for creating a Credit Note. Validates against original invoice."""

    original_invoice_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True,
    )
    credit_reason = forms.ChoiceField(
        choices=CREDIT_REASONS,
        required=True,
        widget=forms.Select(attrs={"class": "form-select form-control"}),
    )
    credit_reason_other = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Specify reason"}),
    )
    refund_method = forms.ChoiceField(
        choices=REFUND_METHODS,
        required=True,
        widget=forms.Select(attrs={"class": "form-select form-control"}),
    )
    credit_line_data = forms.JSONField(
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
            raise ValidationError("Cannot credit a credit or debit note.")
        if self._device and orig.device_id != self._device.pk:
            raise ValidationError("Original invoice belongs to a different device.")
        self._original_receipt = orig
        return inv_id

    def clean_credit_reason(self) -> str:
        reason = self.cleaned_data.get("credit_reason", "").strip()
        if not reason:
            raise ValidationError("Credit reason is required.")
        return reason

    def clean_credit_reason_other(self) -> str:
        reason = self.cleaned_data.get("credit_reason")
        other = (self.cleaned_data.get("credit_reason_other") or "").strip()
        if reason == "OTHER" and not other:
            raise ValidationError("Please specify the reason when selecting Other.")
        return other

    def clean_credit_line_data(self) -> list[dict]:
        data = self.cleaned_data.get("credit_line_data")
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

        line_data = cleaned.get("credit_line_data") or []
        reason = cleaned.get("credit_reason", "")
        reason_other = cleaned.get("credit_reason_other", "")
        refund_method = cleaned.get("refund_method", "")

        if reason == "OTHER" and not reason_other:
            self.add_error("credit_reason_other", "Specify the reason when selecting Other.")
            return cleaned

        from fiscal.services.credit_allocation_service import get_remaining_balance, validate_credit_amount

        remaining = get_remaining_balance(original)
        credit_total = Decimal("0")
        receipt_lines = original.receipt_lines or []

        for i, row in enumerate(line_data):
            if not isinstance(row, dict):
                continue
            try:
                line_idx = int(row.get("line_index", i))
            except (TypeError, ValueError):
                continue
            if line_idx < 0 or line_idx >= len(receipt_lines):
                self.add_error(
                    "credit_line_data",
                    ValidationError(f"Invalid line index {line_idx}."),
                )
                return cleaned
            orig_line = receipt_lines[line_idx]
            line_total_incl = Decimal(str(orig_line.get("receiptLineTotal", 0) or 0))
            credit_amt_incl = None
            if row.get("credit_amount_incl") is not None:
                credit_amt_incl = Decimal(str(row["credit_amount_incl"]))
            else:
                credit_qty = Decimal(str(row.get("credit_quantity", 0)))
                if credit_qty > 0:
                    qty_sold = Decimal(str(orig_line.get("receiptLineQuantity", 1) or 1))
                    credit_amt_incl = (credit_qty / qty_sold) * line_total_incl if qty_sold else Decimal("0")
            if credit_amt_incl is None or credit_amt_incl <= 0:
                continue
            if credit_amt_incl > line_total_incl:
                self.add_error(
                    "credit_line_data",
                    ValidationError(
                        f"Line {line_idx + 1}: Credit amount ({credit_amt_incl}) cannot exceed line total ({line_total_incl})."
                    ),
                )
                return cleaned
            credit_total += credit_amt_incl

        if credit_total <= 0:
            self.add_error(
                "credit_line_data",
                ValidationError("Credit amount must be greater than zero."),
            )
            return cleaned

        try:
            validate_credit_amount(original, credit_total)
        except Exception as e:
            self.add_error("credit_line_data", ValidationError(str(e)))
            return cleaned

        cleaned["_credit_total"] = credit_total
        cleaned["_credit_lines"] = self._build_credit_lines(line_data, receipt_lines)
        cleaned["_reason_text"] = (
            reason_other if reason == "OTHER" else dict(CREDIT_REASONS).get(reason, reason)
        )
        return cleaned

    def _build_credit_lines(
        self, line_data: list[dict], receipt_lines: list[dict]
    ) -> list[dict]:
        lines: list[dict] = []
        for i, row in enumerate(line_data):
            if not isinstance(row, dict):
                continue
            try:
                line_idx = int(row.get("line_index", i))
                credit_amt_incl = row.get("credit_amount_incl")
                if credit_amt_incl is not None:
                    amt = Decimal(str(credit_amt_incl))
                else:
                    credit_qty = Decimal(str(row.get("credit_quantity", 0)))
                    if credit_qty <= 0:
                        continue
                    if line_idx < 0 or line_idx >= len(receipt_lines):
                        continue
                    orig = receipt_lines[line_idx]
                    qty_sold = Decimal(str(orig.get("receiptLineQuantity", 1) or 1))
                    line_total = Decimal(str(orig.get("receiptLineTotal", 0) or 0))
                    amt = (credit_qty / qty_sold) * line_total if qty_sold and line_total else Decimal("0")
            except (TypeError, ValueError):
                continue
            if amt <= 0:
                continue
            if line_idx < 0 or line_idx >= len(receipt_lines):
                continue
            orig = receipt_lines[line_idx]
            name = str(orig.get("receiptLineName", ""))[:200] or "Credit"
            qty_sold = Decimal(str(orig.get("receiptLineQuantity", 1) or 1))
            line_total = Decimal(str(orig.get("receiptLineTotal", 0) or 0))
            credit_qty = (amt / line_total * qty_sold) if line_total else Decimal("0")
            lines.append({
                "description": name,
                "line_total": float(amt),
                "quantity": float(credit_qty),
                "row_num": i + 1,
            })
        return lines
