from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Company(models.Model):
    """Legal entity for device registration and tax compliance."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="%(class)s_records",
    )
    name = models.CharField(max_length=255)
    tin = models.CharField(max_length=50)
    vat_number = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField()
    phone = models.CharField(max_length=50)
    email = models.EmailField()
    currency_default = models.CharField(max_length=3, default="ZWG")
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class FiscalDevice(models.Model):
    """Fiscal device registered with ZIMRA FDMS."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="fiscaldevice_records",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="devices",
        null=True,
        blank=True,
    )
    device_id = models.IntegerField(unique=True)
    device_serial_no = models.CharField(max_length=20, blank=True)
    device_model_name = models.CharField(max_length=100, blank=True)
    device_model_version = models.CharField(max_length=50, blank=True)
    certificate_pem = models.TextField()
    private_key_pem = models.TextField()
    certificate_valid_till = models.DateTimeField(null=True, blank=True)
    is_registered = models.BooleanField(default=False)
    last_fiscal_day_no = models.IntegerField(null=True, blank=True)
    last_receipt_global_no = models.IntegerField(null=True, blank=True)
    fiscal_day_status = models.CharField(max_length=50, null=True, blank=True)
    taxpayer_name = models.CharField(max_length=250, null=True, blank=True)
    taxpayer_tin = models.CharField(max_length=10, null=True, blank=True)
    vat_number = models.CharField(max_length=9, null=True, blank=True)
    branch_name = models.CharField(max_length=250, null=True, blank=True)
    branch_address = models.JSONField(null=True, blank=True)
    is_vat_registered = models.BooleanField(default=False)
    verification_operation_id = models.CharField(max_length=60, null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fiscal Device"
        verbose_name_plural = "Fiscal Devices"

    def __str__(self):
        return f"FiscalDevice #{self.device_id}"

    def get_private_key_pem_decrypted(self) -> str:
        """Return decrypted private key PEM. Use only when needed; never log."""
        from fiscal.services.key_storage import decrypt_private_key
        return decrypt_private_key(self.private_key_pem)


class InvoiceSequence(models.Model):
    """Per-year invoice number sequence for INV-yyyy-N format."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="invoicesequence_records",
    )
    year = models.IntegerField()
    last_number = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Invoice Sequence"
        verbose_name_plural = "Invoice Sequences"
        unique_together = [["tenant", "year"]]

    def __str__(self):
        return f"INV-{self.year}-{self.last_number}"


class DocumentSequence(models.Model):
    """Per-year, per-document-type sequence for CN-yyyy-N and DB-yyyy-N. Invoice uses InvoiceSequence."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="documentsequence_records",
    )
    year = models.IntegerField()
    document_type = models.CharField(max_length=20, db_index=True)  # CREDIT_NOTE, DEBIT_NOTE
    last_number = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Document Sequence"
        verbose_name_plural = "Document Sequences"
        unique_together = [["tenant", "year", "document_type"]]

    def __str__(self):
        return f"{self.document_type}-{self.year}-{self.last_number}"


class DocumentSequenceAdjustment(models.Model):
    """Audit trail for manual sequence adjustments."""

    MODES = (
        ("set_next", "Set Next"),
        ("skip_by", "Skip By"),
    )
    DOCUMENT_TYPES = (
        ("INVOICE", "Invoice"),
        ("CREDIT_NOTE", "Credit Note"),
        ("DEBIT_NOTE", "Debit Note"),
    )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="documentsequenceadjustment_records",
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, db_index=True)
    year = models.IntegerField(db_index=True)
    mode = models.CharField(max_length=20, choices=MODES)
    value = models.IntegerField()
    old_last_number = models.IntegerField()
    new_last_number = models.IntegerField()
    reason = models.TextField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sequence_adjustments",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Document Sequence Adjustment"
        verbose_name_plural = "Document Sequence Adjustments"
        ordering = ["-changed_at"]

    def __str__(self):
        return (
            f"{self.document_type} {self.year} "
            f"{self.old_last_number}->{self.new_last_number}"
        )


class FiscalDay(models.Model):
    """Fiscal day record for a device."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="fiscalday_records",
    )
    device = models.ForeignKey(
        FiscalDevice, on_delete=models.CASCADE, related_name="fiscal_days"
    )
    fiscal_day_no = models.IntegerField()
    status = models.CharField(max_length=50)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    closing_error_code = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        verbose_name = "Fiscal Day"
        verbose_name_plural = "Fiscal Days"
        unique_together = [["device", "fiscal_day_no"]]
        indexes = [
            models.Index(fields=["tenant", "fiscal_day_no"]),
        ]

    def __str__(self):
        return f"Day #{self.fiscal_day_no} ({self.status})"


class Receipt(models.Model):
    """Receipt captured during a fiscal day (invoice, credit note, or debit note)."""

    DOCUMENT_TYPES = (
        ("INVOICE", "Invoice"),
        ("CREDIT_NOTE", "Credit Note"),
        ("DEBIT_NOTE", "Debit Note"),
    )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="receipt_records",
    )
    device = models.ForeignKey(
        FiscalDevice, on_delete=models.CASCADE, related_name="receipts"
    )
    fiscal_day_no = models.IntegerField(null=True, blank=True)
    receipt_global_no = models.IntegerField(null=True, blank=True)
    qb_id = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True)
    fiscal_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("FISCALISED", "Fiscalised"),
            ("FAILED", "Failed"),
        ],
        null=True,
        blank=True,
        db_index=True,
    )
    receipt_counter = models.IntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    receipt_taxes = models.JSONField(default=list)
    receipt_lines = models.JSONField(default=list)
    receipt_payments = models.JSONField(default=list)
    receipt_lines_tax_inclusive = models.BooleanField(default=True)
    receipt_type = models.CharField(max_length=20, default="FiscalInvoice")
    invoice_no = models.CharField(max_length=50, blank=True)
    original_invoice_no = models.CharField(max_length=50, blank=True)
    customer_snapshot = models.JSONField(default=dict, blank=True)
    original_receipt_global_no = models.IntegerField(null=True, blank=True)
    receipt_date = models.DateTimeField(null=True, blank=True)
    receipt_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    canonical_string = models.TextField(blank=True)
    receipt_hash = models.TextField(blank=True)
    receipt_signature_hash = models.TextField(blank=True)
    receipt_signature_sig = models.TextField(blank=True)
    receipt_server_signature = models.JSONField(null=True, blank=True)
    fdms_receipt_id = models.BigIntegerField(null=True, blank=True)
    qr_code_value = models.TextField(blank=True)
    # FDMS SubmitReceipt response fields (Section 10 InvoiceA4 / audit)
    operation_id = models.CharField(max_length=120, blank=True)
    server_date = models.DateTimeField(null=True, blank=True)
    pdf_file = models.FileField(
        upload_to="fiscal_invoices/",
        null=True,
        blank=True,
        help_text="ZIMRA-compliant InvoiceA4 PDF (Section 10/11/13). Path: media/fiscal_invoices/{receipt_id}.pdf",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    document_type = models.CharField(
        max_length=20,
        choices=DOCUMENT_TYPES,
        default="INVOICE",
        db_index=True,
    )
    original_invoice = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="adjustments",
    )
    reason = models.TextField(null=True, blank=True)
    credit_status = models.CharField(
        max_length=30,
        choices=[
            ("ISSUED", "Issued"),
            ("PARTIALLY_CREDITED", "Partially Credited"),
            ("FULLY_CREDITED", "Fully Credited"),
            ("ADJUSTED_UP", "Adjusted Up"),
        ],
        default="ISSUED",
        db_index=True,
    )
    original_total = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    total_debited = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )

    # ZIMRA Section 10 compliant A4 Tax Invoice – FDMS response mapping & VAT breakdown
    fiscal_invoice_number = models.CharField(max_length=80, blank=True, db_index=True)
    receipt_number = models.CharField(max_length=80, blank=True)
    fiscal_signature = models.TextField(blank=True, help_text="FDMS fiscal signature (device/signer).")
    verification_code = models.CharField(max_length=80, blank=True)
    # VAT breakdown by rate (Decimal, 2 dp) – populated by VAT engine after fiscalisation
    subtotal_15 = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tax_15 = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    subtotal_0 = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    subtotal_exempt = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_tax = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Buyer (Section 10) – explicit fields for validation and display
    buyer_name = models.CharField(max_length=255, blank=True)
    buyer_vat = models.CharField(max_length=50, blank=True)
    buyer_tin = models.CharField(max_length=50, blank=True)
    buyer_address = models.TextField(blank=True)

    class Meta:
        verbose_name = "Receipt"
        verbose_name_plural = "Receipts"
        unique_together = [["device", "receipt_global_no"]]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "fiscal_day_no"]),
            models.Index(fields=["tenant", "receipt_global_no"]),
        ]

    def __str__(self):
        if self.receipt_global_no is not None and self.fiscal_day_no is not None:
            return f"Receipt #{self.receipt_global_no} (Day {self.fiscal_day_no})"
        if self.qb_id:
            return f"Receipt qb_id={self.qb_id} (pending)"
        return f"Receipt (id={self.pk})"

    @property
    def receipt_device_signature_hash_hex(self) -> str:
        """Hex representation of receiptDeviceSignature hash for ZIMRA QR."""
        from fiscal.services.qr_generator import get_receipt_device_signature_hash_hex
        return get_receipt_device_signature_hash_hex(self)

    @property
    def is_fiscalised(self) -> bool:
        """True if receipt has been submitted to FDMS and confirmed."""
        return bool(self.fdms_receipt_id)

    @property
    def credited_total(self) -> Decimal:
        """Sum of fiscalised credit notes against this invoice. Decimal only."""
        if self.document_type not in ("INVOICE", "") or self.receipt_type in ("CreditNote", "CREDITNOTE"):
            return Decimal("0")
        credits = self.adjustments.filter(
            Q(receipt_type="CreditNote") | Q(receipt_type="CREDITNOTE")
        ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0)
        total = Decimal("0")
        for cn in credits:
            amt = cn.receipt_total or Decimal("0")
            total += -amt
        return total

    @property
    def remaining_balance(self) -> Decimal:
        """Invoice balance: original_total - credited + total_debited. Decimal only."""
        orig = self.original_total if self.original_total is not None else (self.receipt_total or Decimal("0"))
        debited = self.total_debited or Decimal("0")
        return orig - self.credited_total + debited

    def get_tax_ids(self) -> list[int]:
        """Tax IDs used on this receipt. For debit validation."""
        ids = []
        for t in self.receipt_taxes or []:
            tid = t.get("taxID") or t.get("fiscalCounterTaxID")
            if tid is not None:
                ids.append(int(tid))
        if not ids and self.receipt_taxes:
            ids = [int(t.get("taxID", 1)) for t in self.receipt_taxes]
        return ids if ids else [1]

    def is_older_than_12_months(self) -> bool:
        """True if receipt_date is older than 12 months. RCPT033."""
        from datetime import datetime, timezone, timedelta
        rec_dt = self.receipt_date or self.created_at
        if not rec_dt:
            return False
        if rec_dt.tzinfo is None:
            rec_dt = rec_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - rec_dt).days > 365

    def get_credit_notes(self):
        """Fiscalised credit notes against this invoice."""
        if self.document_type not in ("INVOICE", "") or self.receipt_type in ("CreditNote", "CREDITNOTE"):
            return Receipt.objects.none()
        return self.adjustments.filter(
            Q(receipt_type="CreditNote") | Q(receipt_type="CREDITNOTE")
        ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0).order_by("created_at")

    def get_debit_notes(self):
        """Fiscalised debit notes against this invoice."""
        if self.document_type not in ("INVOICE", "") or self.receipt_type in ("DebitNote", "DEBITNOTE"):
            return Receipt.objects.none()
        return self.adjustments.filter(
            Q(receipt_type="DebitNote") | Q(receipt_type="DEBITNOTE")
        ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0).order_by("created_at")

    def clean(self) -> None:
        if self.document_type in ("CREDIT_NOTE", "DEBIT_NOTE"):
            if not self.original_invoice_id and not (getattr(self, "original_invoice", None) and getattr(self.original_invoice, "pk", None)):
                raise ValidationError(
                    {"original_invoice": "Original invoice is required for Credit Note and Debit Note."}
                )
            if not (self.reason or "").strip():
                raise ValidationError(
                    {"reason": "Reason is required for Credit Note and Debit Note."}
                )
        if self.document_type == "INVOICE":
            if self.original_invoice_id or (getattr(self, "original_invoice", None) and getattr(self.original_invoice, "pk", None)):
                raise ValidationError(
                    {"original_invoice": "Invoice must not reference an original invoice."}
                )

    # Protected fields: cannot change after fiscalisation (audit trail via FiscalEditAttempt)
    _FISCALISED_PROTECTED_FIELDS = (
        "receipt_lines", "receipt_taxes", "receipt_payments", "receipt_total",
        "receipt_hash", "receipt_signature_hash", "receipt_signature_sig",
        "receipt_server_signature", "canonical_string", "fiscal_day_no",
        "receipt_global_no", "invoice_no", "customer_snapshot",
    )

    def save(self, *args, **kwargs):
        if self.pk and self.fdms_receipt_id:
            try:
                old = Receipt.objects.get(pk=self.pk)
            except Receipt.DoesNotExist:
                pass
            else:
                diff = {}
                for field in self._FISCALISED_PROTECTED_FIELDS:
                    if not hasattr(self, field) or not hasattr(old, field):
                        continue
                    new_val = getattr(self, field)
                    old_val = getattr(old, field)
                    if new_val != old_val:
                        diff[field] = {"old": str(old_val)[:500], "new": str(new_val)[:500]}
                if diff:
                    FiscalEditAttempt.objects.create(
                        receipt=self,
                        original_snapshot={f: getattr(old, f) for f in self._FISCALISED_PROTECTED_FIELDS if hasattr(old, f)},
                        attempted_change=diff,
                        source="API",
                        actor="",
                        blocked=True,
                        diff_summary="; ".join(f"{k} changed" for k in diff),
                    )
                    raise ValidationError(
                        "Cannot edit receipt after fiscalisation. Changes to lines, taxes, payments, "
                        "total, or signatures are blocked. Audit log created."
                    )
        super().save(*args, **kwargs)


class CreditNoteImport(models.Model):
    """Audit record for Excel credit note imports. Immutable."""

    original_receipt = models.ForeignKey(
        Receipt, on_delete=models.CASCADE, related_name="credit_note_imports"
    )
    raw_excel_file = models.FileField(upload_to="credit_note_imports/%Y/%m/", null=True, blank=True)
    parsed_lines = models.JSONField(default=list)
    original_invoice_snapshot = models.JSONField(default=dict)
    remaining_balance_before = models.DecimalField(max_digits=14, decimal_places=2)
    credit_total = models.DecimalField(max_digits=14, decimal_places=2)
    credit_reason = models.TextField(blank=True)
    user_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    credit_note_receipt = models.ForeignKey(
        Receipt, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_from_import"
    )

    class Meta:
        verbose_name = "Credit Note Import"
        verbose_name_plural = "Credit Note Imports"
        ordering = ["-created_at"]


class InvoiceImport(models.Model):
    """Audit record for Excel invoice imports. Immutable."""

    raw_excel_file = models.FileField(upload_to="invoice_imports/%Y/%m/", null=True, blank=True)
    sheet_name = models.CharField(max_length=100, blank=True)
    header_row = models.IntegerField(null=True, blank=True)
    parsed_lines = models.JSONField(default=list)
    receipt_type = models.CharField(max_length=20, default="FiscalInvoice")
    currency = models.CharField(max_length=3, default="USD")
    tax_id = models.IntegerField(null=True, blank=True)
    user_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    fiscal_receipt = models.ForeignKey(
        Receipt, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_from_invoice_import"
    )

    class Meta:
        verbose_name = "Invoice Import"
        verbose_name_plural = "Invoice Imports"
        ordering = ["-created_at"]


class Customer(models.Model):
    """Customer for invoice creation. Name, TIN, address, contact details."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="customer_records",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="customers",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    tin = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """Product with HS code for FDMS-compliant invoice creation."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="product_records",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="products",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_code = models.CharField(max_length=50, default="VAT")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=15)
    hs_code = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FDMSConfigs(models.Model):
    """Persisted GetConfig response. Source of truth for tax IDs, currencies, constraints."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="fdmsconfigs_records",
    )
    device_id = models.IntegerField(db_index=True)
    raw_response = models.JSONField(default=dict)
    tax_table = models.JSONField(default=list)
    allowed_currencies = models.JSONField(default=list)
    fetched_at = models.DateTimeField()

    class Meta:
        verbose_name = "FDMS Configs"
        verbose_name_plural = "FDMS Configs"
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"FDMSConfigs device={self.device_id} fetched={self.fetched_at}"


class TaxMapping(models.Model):
    """Maps local tax codes (used in products) to FDMS taxID from GetConfig."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="taxmapping_records",
    )
    local_code = models.CharField(max_length=20, help_text="Code used in products, e.g. VAT")
    display_name = models.CharField(max_length=100, blank=True, help_text="Label for UI, e.g. VAT 15%")
    fdms_tax_id = models.IntegerField(help_text="taxID from FDMS GetConfig applicableTaxes")
    fdms_tax_code = models.CharField(max_length=3, blank=True, help_text="FDMS taxCode (max 3 chars, e.g. 517). Leave blank to use from GetConfig.")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Tax percentage from GetConfig (e.g. 15.00). Used when GetConfig unavailable.")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tax Mapping"
        verbose_name_plural = "Tax Mappings"
        ordering = ["sort_order", "local_code"]
        unique_together = [["tenant", "local_code"]]

    def __str__(self):
        return f"{self.local_code} → FDMS taxID {self.fdms_tax_id}"


class FiscalEditAttempt(models.Model):
    """Audit log for attempted edits to fiscalised invoices. Immutable."""

    receipt = models.ForeignKey(
        Receipt, on_delete=models.CASCADE, related_name="edit_attempts"
    )
    original_snapshot = models.JSONField(default=dict)
    attempted_change = models.JSONField(default=dict)
    source = models.CharField(max_length=50, default="QB")  # QB, Manual, API
    actor = models.CharField(max_length=255, blank=True)
    blocked = models.BooleanField(default=True)
    diff_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fiscal Edit Attempt"
        verbose_name_plural = "Fiscal Edit Attempts"
        ordering = ["-created_at"]


class QuickBooksConnection(models.Model):
    """OAuth 2.0 connection to QuickBooks Online. One active connection per realm."""

    realm_id = models.CharField(max_length=50, unique=True, db_index=True)
    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "QuickBooks Connection"
        verbose_name_plural = "QuickBooks Connections"
        ordering = ["-updated_at"]


class QuickBooksEvent(models.Model):
    """Raw QuickBooks webhook payload. Immutable audit."""

    event_type = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "QuickBooks Event"
        verbose_name_plural = "QuickBooks Events"
        ordering = ["-created_at"]


class QuickBooksInvoice(models.Model):
    """QB invoice snapshot. Stored before fiscalisation. Idempotency key = qb_invoice_id."""

    qb_invoice_id = models.CharField(max_length=100, unique=True, db_index=True)
    qb_customer_id = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    raw_payload = models.JSONField(default=dict)
    fiscalised = models.BooleanField(default=False)
    fiscal_receipt = models.ForeignKey(
        Receipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="qb_invoices",
    )
    fiscal_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "QuickBooks Invoice"
        verbose_name_plural = "QuickBooks Invoices"
        ordering = ["-created_at"]


class ActivityEvent(models.Model):
    """Activity feed for device operations. Broadcast to WebSocket."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="activityevent_records",
    )
    device = models.ForeignKey(
        FiscalDevice,
        on_delete=models.CASCADE,
        related_name="activity_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=50)
    message = models.TextField(blank=True)
    level = models.CharField(max_length=20, default="info")  # info, warning, error
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Activity Event"
        verbose_name_plural = "Activity Events"
        ordering = ["-created_at"]


class AuditEvent(models.Model):
    """Audit timeline for fiscal lifecycle. Immutable."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="auditevent_records",
    )
    device = models.ForeignKey(
        FiscalDevice,
        on_delete=models.CASCADE,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=100)  # device_registered, fiscal_day_opened, receipt_submitted, etc.
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        ordering = ["-created_at"]


class FDMSApiLog(models.Model):
    """Audit log for FDMS API calls (Ping, OpenDay, CloseDay, SubmitReceipt, etc.)."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="fdmsapilog_records",
    )
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    request_payload = models.JSONField(default=dict)
    response_payload = models.JSONField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    operation_id = models.CharField(max_length=128, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "FDMS API Log"
        verbose_name_plural = "FDMS API Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self):
        return f"{self.method} {self.endpoint} - {self.status_code or 'error'}"


class ReceiptSubmissionResponse(models.Model):
    """
    Stores FDMS SubmitReceipt response per attempt. Links to receipt when successful.
    Used to show validation errors for an invoice/credit/debit note after submission.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="receiptsubmissionresponse_records",
    )
    device = models.ForeignKey(
        FiscalDevice, on_delete=models.CASCADE, related_name="submission_responses"
    )
    receipt_global_no = models.IntegerField(db_index=True)
    receipt = models.ForeignKey(
        Receipt, on_delete=models.CASCADE, null=True, blank=True, related_name="submission_responses"
    )
    fiscal_day_no = models.IntegerField(null=True, blank=True)
    status_code = models.IntegerField()
    response_payload = models.JSONField(default=dict)
    validation_errors = models.JSONField(default=list)  # list of error strings for display
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Receipt Submission Response"
        verbose_name_plural = "Receipt Submission Responses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"SubmitReceipt device={self.device_id} global_no={self.receipt_global_no} status={self.status_code}"


class DebitNote(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="debitnote_records",
    )
    device_id = models.IntegerField()
    receipt_global_no = models.IntegerField(db_index=True)
    receipt_date = models.DateField()

    original_invoice_no = models.IntegerField()
    original_invoice_date = models.DateField()

    currency = models.CharField(max_length=3)

    debit_reason = models.TextField()

    subtotal = models.DecimalField(max_digits=15, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2)
    total = models.DecimalField(max_digits=15, decimal_places=2)

    receipt_device_signature_hex = models.TextField()
    qr_code_value = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Debit Note"
        verbose_name_plural = "Debit Notes"
        ordering = ["-created_at"]
        unique_together = [["tenant", "receipt_global_no"]]


class CreditNote(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name="creditnote_records",
    )
    device_id = models.IntegerField()
    receipt_global_no = models.IntegerField(db_index=True)
    receipt_date = models.DateField()

    original_invoice_no = models.IntegerField()
    original_invoice_date = models.DateField()

    currency = models.CharField(max_length=3)

    credit_reason = models.TextField()

    subtotal = models.DecimalField(max_digits=15, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2)
    total = models.DecimalField(max_digits=15, decimal_places=2)

    receipt_device_signature_hex = models.TextField()
    qr_code_value = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Credit Note"
        verbose_name_plural = "Credit Notes"
        ordering = ["-created_at"]
        unique_together = [["tenant", "receipt_global_no"]]

        



