"""Structured JSON logging formatter for FDMS observability."""

import json
import logging
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Output log records as single-line JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "operation_id") and record.operation_id:
            log_obj["operation_id"] = record.operation_id
        if hasattr(record, "endpoint") and record.endpoint:
            log_obj["endpoint"] = record.endpoint
        if hasattr(record, "device_id") and record.device_id is not None:
            log_obj["device_id"] = record.device_id
        if hasattr(record, "status_code") and record.status_code is not None:
            log_obj["status_code"] = record.status_code
        return json.dumps(log_obj, default=str)
