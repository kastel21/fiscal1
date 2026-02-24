"""Models for legal app: EULA acceptance tracking."""

from django.conf import settings
from django.db import models


class EulaAcceptance(models.Model):
    """Records that a user has accepted the End-User License Agreement."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eula_acceptance",
    )
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "EULA acceptance"
        verbose_name_plural = "EULA acceptances"

    def __str__(self):
        return f"{self.user} accepted {self.accepted_at}"
