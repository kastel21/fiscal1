"""
Certificate utilities for FDMS device registration.
Generates ECC keys and CSRs per ZIMRA requirements.
"""

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def generate_key_pair() -> tuple[bytes, bytes]:
    """
    Generate ECC secp256r1 (NIST P-256) key pair.

    Returns:
        tuple: (private_key_pem, public_key_pem) as bytes
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key_pem, public_key_pem


def generate_csr(
    device_id: int,
    device_serial_no: str,
    private_key_pem: bytes | str,
) -> str:
    """
    Generate Certificate Signing Request for FDMS registration.

    CN format: ZIMRA-{SERIAL}-{ZERO_PADDED_10_DIGIT_DEVICEID}
    Subject: C=ZW, O=Zimbabwe Revenue Authority, S=Zimbabwe

    Args:
        device_id: Device ID (sold/active).
        device_serial_no: Device serial number (e.g. SN-001).
        private_key_pem: Private key in PEM format (bytes or str).

    Returns:
        str: CSR in PEM format.
    """
    if isinstance(private_key_pem, str):
        private_key_pem = private_key_pem.encode()
    private_key = serialization.load_pem_private_key(
        private_key_pem, password=None
    )
    cn = f"ZIMRA-{device_serial_no}-{device_id:010d}"
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "ZW"),
                    x509.NameAttribute(
                        NameOID.ORGANIZATION_NAME, "Zimbabwe Revenue Authority"
                    ),
                    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Zimbabwe"),
                    x509.NameAttribute(NameOID.COMMON_NAME, cn),
                ]
            )
        )
        .sign(private_key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()
