"""Utility functions for fiscal app."""

import json

SENSITIVE_KEYS = frozenset({
    "private_key_pem", "activationkey", "certificaterequest",
    "certificate", "certificate_pem",  # device certificate
})
SIGNATURE_KEYS = frozenset({"hash", "signature"})
SIGNATURE_OBJECT_KEYS = frozenset({
    "fiscaldaydevicesignature", "receiptdevicesignature",
    "fiscaldayserversignature", "receiptserversignature",
})


def mask_sensitive_fields(payload):
    """
    Mask sensitive fields before saving to logs. Call before FDMSApiLog.create.
    Masks: activationKey, private_key_pem, certificate_pem, certificate,
    receiptDeviceSignature.signature, fiscalDayDeviceSignature.signature, etc.
    """
    return mask_sensitive_data(payload, mask_signatures=True)


def mask_sensitive_data(obj, mask_signatures: bool = True):
    """
    Recursively mask sensitive fields in a JSON-serializable object.

    Masks: private_key_pem, activationKey, certificateRequest.
    Optionally masks: hash, signature in fiscalDayDeviceSignature.
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [mask_sensitive_data(i, mask_signatures) for i in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            k_lower = k.lower().replace("_", "").replace("-", "")
            if k_lower in SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            elif mask_signatures and k_lower in SIGNATURE_KEYS:
                out[k] = "[REDACTED]"
            elif mask_signatures and isinstance(v, dict) and k_lower in SIGNATURE_OBJECT_KEYS:
                out[k] = {sk: "[REDACTED]" for sk in v}
            else:
                out[k] = mask_sensitive_data(v, mask_signatures)
        return out
    return obj


def safe_json_dumps(obj, indent: int = 2) -> str:
    """JSON dump with sensitive data masked."""
    return json.dumps(mask_sensitive_data(obj), indent=indent, default=str)
