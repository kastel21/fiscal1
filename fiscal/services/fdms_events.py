"""Emit FDMS events to WebSocket groups."""

import logging

logger = logging.getLogger("fiscal")


def emit_to_device(device_id: int, event_type: str, data: dict) -> None:
    """Send event to fdms_device_<device_id> WebSocket group."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if not layer:
            return
        group = f"fdms_device_{device_id}"
        async_to_sync(layer.group_send)(
            group,
            {"type": "fdms_event", "data": {"type": event_type, **data}},
        )
    except Exception as e:
        logger.warning("Emit to device %s failed: %s", device_id, e)


def emit_metrics_updated() -> None:
    """Broadcast metrics.updated to fdms_dashboard WebSocket group."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from dashboard.services.metrics_service import get_metrics

        layer = get_channel_layer()
        if not layer:
            return
        metrics = get_metrics()
        async_to_sync(layer.group_send)(
            "fdms_dashboard",
            {"type": "fdms_event", "data": {"type": "metrics.updated", "metrics": metrics}},
        )
    except Exception as e:
        logger.warning("Emit metrics.updated failed: %s", e)
