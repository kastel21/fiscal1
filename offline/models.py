"""Offline mode models."""

from django.db import models

QUEUE_STATES = (
    ("QUEUED", "Queued"),
    ("SUBMITTING", "Submitting"),
    ("SUBMITTED", "Submitted"),
    ("FAILED", "Failed"),
)


class OfflineReceiptQueue(models.Model):
    """Append-only offline receipt queue."""

    receipt = models.OneToOneField(
        "fiscal.Receipt",
        on_delete=models.CASCADE,
        related_name="offline_queue_entry",
    )
    state = models.CharField(max_length=20, choices=QUEUE_STATES, default="QUEUED", db_index=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Offline Receipt Queue"
        verbose_name_plural = "Offline Receipt Queue"
        ordering = ["receipt__receipt_global_no", "receipt__fiscal_day_no", "created_at"]


class OfflineBatchFile(models.Model):
    """Immutable batch file for offline recovery."""

    device = models.ForeignKey(
        "fiscal.FiscalDevice",
        on_delete=models.CASCADE,
        related_name="offline_batch_files",
    )
    file_path = models.CharField(max_length=512)
    file_checksum = models.CharField(max_length=64, blank=True)
    receipt_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Offline Batch File"
        verbose_name_plural = "Offline Batch Files"
        ordering = ["-created_at"]


class SubmissionAttempt(models.Model):
    """Audit log for every submission attempt."""

    queue_entry = models.ForeignKey(
        OfflineReceiptQueue,
        on_delete=models.CASCADE,
        related_name="submission_attempts",
        null=True,
        blank=True,
    )
    receipt = models.ForeignKey(
        "fiscal.Receipt",
        on_delete=models.CASCADE,
        related_name="submission_attempts",
    )
    success = models.BooleanField(default=False)
    response_status_code = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    attempt_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Submission Attempt"
        verbose_name_plural = "Submission Attempts"
        ordering = ["-attempt_at"]
