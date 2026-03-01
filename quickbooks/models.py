"""
QuickBooks OAuth2 token storage and realm association.
"""

import logging
from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class QuickBooksToken(models.Model):
    """
    Stores QuickBooks OAuth2 access and refresh tokens per user/realm.
    Use refresh() before API calls when is_expired() is True.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="quickbooks_tokens",
        db_index=True,
    )
    realm_id = models.CharField(max_length=64, db_index=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_type = models.CharField(max_length=32, default="Bearer")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "quickbooks_quickbookstoken"
        verbose_name = "QuickBooks Token"
        verbose_name_plural = "QuickBooks Tokens"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["realm_id", "is_active"]),
        ]
        # One active token per realm (and optionally per user)
        constraints = []

    def __str__(self):
        return f"QuickBooksToken(realm={self.realm_id}, user={self.user_id}, active={self.is_active})"

    def is_expired(self, buffer_seconds=60):
        """
        Return True if the access token is expired or within buffer_seconds of expiry.
        Uses timezone-aware comparison (expires_at should be stored in UTC).
        """
        if not self.expires_at:
            return True
        now = timezone.now()
        if timezone.is_naive(self.expires_at):
            expires_at = timezone.make_aware(self.expires_at, timezone.utc)
        else:
            expires_at = self.expires_at
        threshold = now - timezone.timedelta(seconds=buffer_seconds)
        return expires_at <= threshold

    def refresh(self):
        """
        Exchange refresh_token for new access_token and refresh_token.
        Updates self in DB. Raises QuickBooksTokenError on failure.
        """
        from quickbooks.utils import refresh_quickbooks_token

        refresh_quickbooks_token(self)
