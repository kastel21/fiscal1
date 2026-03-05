from django import forms
from django.utils import timezone


class SequenceAdjustmentForm(forms.Form):
    DOCUMENT_CHOICES = (
        ("INVOICE", "Invoice"),
        ("CREDIT_NOTE", "Credit Note"),
        ("DEBIT_NOTE", "Debit Note"),
    )
    MODE_CHOICES = (
        ("set_next", "Set next number"),
        ("skip_by", "Skip by count"),
    )

    document_type = forms.ChoiceField(
        choices=DOCUMENT_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "w-full border border-slate-300 rounded px-3 py-2"}),
    )
    year = forms.IntegerField(
        min_value=2000,
        max_value=9999,
        required=True,
        initial=timezone.now().year,
        widget=forms.NumberInput(attrs={"class": "w-full border border-slate-300 rounded px-3 py-2"}),
    )
    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        required=True,
        initial="set_next",
        widget=forms.Select(attrs={"class": "w-full border border-slate-300 rounded px-3 py-2"}),
    )
    value = forms.IntegerField(
        min_value=1,
        required=True,
        help_text="For set_next: desired next number. For skip_by: how many numbers to skip.",
        widget=forms.NumberInput(attrs={"class": "w-full border border-slate-300 rounded px-3 py-2"}),
    )
    reason = forms.CharField(
        required=True,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "class": "w-full border border-slate-300 rounded px-3 py-2"}),
    )

