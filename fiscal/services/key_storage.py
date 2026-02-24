"""
Secure storage for private keys. Encrypts at rest using Fernet.
Requires FDMS_ENCRYPTION_KEY environment variable (Fernet key, base64).
"""

import base64
import logging
import os

logger = logging.getLogger("fiscal")

_FERNET = None
_PLAINTEXT_FALLBACK = True


def _get_fernet():
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = os.environ.get("FDMS_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
        return _FERNET
    except Exception as e:
        logger.warning("FDMS key encryption disabled: %s", e)
        return None


def encrypt_private_key(pem: str | bytes) -> str:
    """Encrypt private key PEM for storage. Returns base64 string or plaintext if no key."""
    f = _get_fernet()
    if not f:
        return pem.decode() if isinstance(pem, bytes) else pem
    data = pem.encode() if isinstance(pem, str) else pem
    enc = f.encrypt(data)
    return "ENC:" + base64.b64encode(enc).decode()


def decrypt_private_key(stored: str) -> str:
    """
    Decrypt stored private key. Returns PEM string.
    If stored starts with -----BEGIN, returns as-is (legacy plaintext).
    """
    if not stored:
        raise ValueError("No private key stored")
    if stored.strip().startswith("-----BEGIN"):
        return stored
    if stored.startswith("ENC:"):
        f = _get_fernet()
        if not f:
            raise ValueError("FDMS_ENCRYPTION_KEY not set; cannot decrypt key")
        enc = base64.b64decode(stored[4:])
        return f.decrypt(enc).decode()
    raise ValueError("Invalid private key format")


def is_encryption_available() -> bool:
    """Return True if FDMS_ENCRYPTION_KEY is configured."""
    return _get_fernet() is not None


def encrypt_string(plain: str) -> str:
    """Encrypt string for storage."""
    f = _get_fernet()
    if not f:
        return plain
    data = plain.encode("utf-8")
    enc = f.encrypt(data)
    return "ENC:" + base64.b64encode(enc).decode()


def decrypt_string(stored: str) -> str:
    """Decrypt stored string."""
    if not stored:
        return ""
    if stored.startswith("ENC:"):
        f = _get_fernet()
        if not f:
            raise ValueError("FDMS_ENCRYPTION_KEY not set; cannot decrypt")
        enc = base64.b64decode(stored[4:])
        return f.decrypt(enc).decode("utf-8")
    return stored
