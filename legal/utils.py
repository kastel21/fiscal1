"""Helpers for EULA acceptance logic."""

from datetime import timedelta

from django.utils import timezone


def user_has_accepted_eula(user):
    """
    Return True if the user is considered to have accepted the EULA:
    - They have an EulaAcceptance record, or
    - Their account is older than 30 days (deemed acceptance by continued use).
    """
    if not user or not user.is_authenticated:
        return True  # No banner for anonymous users
    from .models import EulaAcceptance

    if EulaAcceptance.objects.filter(user=user).exists():
        return True
    threshold = timezone.now() - timedelta(days=30)
    return user.date_joined <= threshold
