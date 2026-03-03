"""Utility functions for fiscal app. Redaction for logs and UI."""

import json
import re

SENSITIVE_KEYS = frozenset({
    "private_key_pem", "activationkey", "certificaterequest",
    "certificate", "certificate_pem",  # device certificate
    "access_token", "refreshtoken", "refresh_token", "id_token",
    "token", "authorization", "secret", "password", "api_key", "apikey",
    "client_secret", "clientsecret", "verifier", "csrf_token", "csrftoken",
})
SIGNATURE_KEYS = frozenset({"hash", "signature"})
SIGNATURE_OBJECT_KEYS = frozenset({
    "fiscaldaydevicesignature", "receiptdevicesignature",
    "fiscaldayserversignature", "receiptserversignature",
})

# Patterns to redact in free-form strings (logs and UI)
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE)
_BASIC_RE = re.compile(r"Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE)
# Paths that might contain secrets
_SECRET_PATH_RE = re.compile(r"(?i)[^\s]*/(?:key|secret|token|credential|\.pem)[^\s]*")


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

    Masks: private_key_pem, activationKey, certificateRequest, access_token, refresh_token, etc.
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


def redact_string_for_log(s: str, max_length: int = 500) -> str:
    """
    Redact sensitive substrings in a string before logging.
    Replaces Bearer tokens, Basic auth, long token-like strings, and secret file paths.
    """
    if not s or not isinstance(s, str):
        return s
    out = _BEARER_RE.sub("Bearer [REDACTED]", s)
    out = _BASIC_RE.sub("Basic [REDACTED]", out)
    out = _SECRET_PATH_RE.sub("[REDACTED_PATH]", out)
    return out[:max_length] + ("..." if len(out) > max_length else "")


def redact_for_ui(s: str, max_length: int = 200) -> str:
    """
    Redact sensitive content for display in UI / API responses.
    Stricter: redacts tokens, paths, and long error messages.
    """
    if not s or not isinstance(s, str):
        return s
    out = redact_string_for_log(s, max_length=max_length)
    return out


def safe_json_dumps(obj, indent: int = 2) -> str:
    """JSON dump with sensitive data masked."""
    return json.dumps(mask_sensitive_data(obj), indent=indent, default=str)
