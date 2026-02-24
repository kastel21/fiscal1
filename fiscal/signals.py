"""Signals for cascade delete and related cleanup."""

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import FDMSConfigs, FiscalDevice


@receiver(pre_delete, sender=FiscalDevice)
def delete_device_configs(sender, instance, **kwargs):
    """Cascade delete FDMSConfigs when FiscalDevice is deleted."""
    FDMSConfigs.objects.filter(device_id=instance.device_id).delete()
