"""
Reusable signature engine for FDMS (ECC/RSA).
Generates SHA256 hash and signature (Base64).
"""

import base64
import hashlib

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa


class SignatureEngine:
    """Signature engine with automatic algorithm detection."""

    def __init__(self, certificate_pem: str | bytes, private_key_pem: str | bytes):
        if isinstance(certificate_pem, str):
            certificate_pem = certificate_pem.encode()
        if isinstance(private_key_pem, str):
            private_key_pem = private_key_pem.encode()

        self.certificate = x509.load_pem_x509_certificate(
            certificate_pem, default_backend()
        )
        self.private_key = serialization.load_pem_private_key(
            private_key_pem, password=None
        )

    def detect_algorithm(self) -> str:
        pub = self.certificate.public_key()
        if isinstance(pub, ec.EllipticCurvePublicKey):
            return "ECC"
        if isinstance(pub, rsa.RSAPublicKey):
            return "RSA"
        raise ValueError("Unsupported key type")

    def sign(self, data_string: str) -> dict:
        hash_bytes = hashlib.sha256(data_string.encode("utf-8")).digest()
        hash_base64 = base64.b64encode(hash_bytes).decode()

        algorithm = self.detect_algorithm()
        if algorithm == "ECC":
            signature = self.private_key.sign(
                data_string.encode("utf-8"),
                ec.ECDSA(hashes.SHA256()),
            )
        else:
            signature = self.private_key.sign(
                data_string.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )

        signature_base64 = base64.b64encode(signature).decode()
        return {
            "hash": hash_base64,
            "signature": signature_base64,
        }
