"""
Mutual TLS support for FDMS Device API endpoints.
Writes certificate and private key to temporary files for requests.
Files created with mode 600, deleted immediately after use.
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def cert_files_for_device(device):
    """
    Yield (cert_path, key_path) for use with requests cert= parameter.

    Writes certificate_pem and private_key_pem to temporary files.
    Files are deleted when the context exits.

    Args:
        device: FiscalDevice instance with certificate_pem and private_key_pem.

    Yields:
        tuple: (cert_file_path, key_file_path)

    Raises:
        ValueError: If device has no certificate or key.
    """
    if not device.certificate_pem or not device.private_key_pem:
        raise ValueError("Device has no certificate or private key")

    cert_pem = device.certificate_pem
    key_pem = device.get_private_key_pem_decrypted()
    if isinstance(cert_pem, bytes):
        cert_pem = cert_pem.decode()
    if isinstance(key_pem, bytes):
        key_pem = key_pem.decode()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pem", delete=False, dir=tempfile.gettempdir()
    ) as cert_file:
        cert_file.write(cert_pem)
        cert_path = cert_file.name
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pem", delete=False, dir=tempfile.gettempdir()
    ) as key_file:
        key_file.write(key_pem)
        key_path = key_file.name
    try:
        os.chmod(cert_path, 0o600)
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    try:
        yield (cert_path, key_path)
    finally:
        Path(cert_path).unlink(missing_ok=True)
        Path(key_path).unlink(missing_ok=True)
