"""Activity and audit event logging."""

from fiscal.models import ActivityEvent, AuditEvent, FiscalDevice


def log_activity(device: FiscalDevice | None, event_type: str, message: str, level: str = "info") -> ActivityEvent:
    """Create ActivityEvent and optionally emit to WebSocket."""
    ev = ActivityEvent.objects.create(
        device=device,
        event_type=event_type,
        message=message,
        level=level,
    )
    if device:
        from fiscal.services.fdms_events import emit_to_device
        emit_to_device(device.device_id, "activity", {"event_type": event_type, "message": message})
    return ev


def log_audit(device: FiscalDevice | None, action: str, metadata: dict | None = None) -> AuditEvent:
    """Create AuditEvent."""
    return AuditEvent.objects.create(
        device=device,
        action=action,
        metadata=metadata or {},
    )
