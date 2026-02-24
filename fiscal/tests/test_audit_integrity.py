"""
Tests for signature verification and receipt chain validation.
"""

import base64
import hashlib
from decimal import Decimal
from datetime import datetime, timedelta

from django.utils import timezone

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from django.test import TestCase

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.audit_integrity import (
    validate_receipt_chain,
    verify_receipt_signature,
)
from fiscal.services.receipt_engine import build_receipt_canonical_string
from fiscal.services.signature_engine import SignatureEngine


def _make_test_device(device_id: int = 99999) -> FiscalDevice:
    """Create a FiscalDevice with self-signed ECC cert + key for testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-device")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(1000)
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .sign(private_key, hashes.SHA256(), default_backend())
    )
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM).decode()

    device = FiscalDevice.objects.create(
        device_id=device_id,
        device_serial_no="TEST-SN",
        certificate_pem=cert_pem,
        private_key_pem=private_key_pem,
        is_registered=True,
    )
    return device


class SignatureVerificationTests(TestCase):
    """Tests for verify_receipt_signature."""

    def test_verify_valid_signature(self):
        """Valid signature returns (True, None)."""
        device = _make_test_device()
        canonical = "12345FiscalInvoiceUSD12025-02-11T10:30:001500"
        engine = SignatureEngine(
            certificate_pem=device.certificate_pem,
            private_key_pem=device.get_private_key_pem_decrypted(),
        )
        result = engine.sign(canonical)
        ok, err = verify_receipt_signature(
            device=device,
            canonical=canonical,
            stored_hash_b64=result["hash"],
            stored_sig_b64=result["signature"],
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_verify_rejects_hash_mismatch(self):
        """Hash mismatch returns (False, error)."""
        device = _make_test_device()
        canonical = "12345FiscalInvoiceUSD12025-02-11T10:30:001500"
        wrong_hash = base64.b64encode(b"wrong_hash_value_32bytes!!").decode()
        engine = SignatureEngine(
            certificate_pem=device.certificate_pem,
            private_key_pem=device.get_private_key_pem_decrypted(),
        )
        result = engine.sign(canonical)
        ok, err = verify_receipt_signature(
            device=device,
            canonical=canonical,
            stored_hash_b64=wrong_hash,
            stored_sig_b64=result["signature"],
        )
        self.assertFalse(ok)
        self.assertIn("Hash mismatch", err)

    def test_verify_rejects_tampered_canonical(self):
        """Tampered canonical (wrong hash/sig combo) fails verification."""
        device = _make_test_device()
        canonical = "12345FiscalInvoiceUSD12025-02-11T10:30:001500"
        engine = SignatureEngine(
            certificate_pem=device.certificate_pem,
            private_key_pem=device.get_private_key_pem_decrypted(),
        )
        result = engine.sign(canonical)
        tampered = "12345FiscalInvoiceUSD12025-02-11T10:30:001501"
        ok, err = verify_receipt_signature(
            device=device,
            canonical=tampered,
            stored_hash_b64=result["hash"],
            stored_sig_b64=result["signature"],
        )
        self.assertFalse(ok)


class ReceiptChainValidationTests(TestCase):
    """Tests for validate_receipt_chain."""

    def test_valid_chain_passes(self):
        """Valid receipt chain produces no errors."""
        device = _make_test_device()
        prev_hash = None
        for i, (global_no, counter, total_cents) in enumerate(
            [(1, 1, 1500), (2, 2, 2000), (3, 3, 2500)]
        ):
            taxes = [
                {
                    "taxID": 1,
                    "taxCode": "VAT",
                    "taxPercent": 15,
                    "taxAmount": 1.0 * (i + 1),
                    "salesAmountWithTax": 10.0 * (i + 1),
                }
            ]
            canonical = build_receipt_canonical_string(
                device_id=device.device_id,
                receipt_type="FiscalInvoice",
                receipt_currency="USD",
                receipt_global_no=global_no,
                receipt_date="2025-02-11T10:30:00",
                receipt_total=Decimal(total_cents) / 100,
                receipt_tax_lines=taxes,
                previous_receipt_hash=prev_hash,
            )
            expected_hash = base64.b64encode(
                hashlib.sha256(canonical.encode("utf-8")).digest()
            ).decode()
            engine = SignatureEngine(
                certificate_pem=device.certificate_pem,
                private_key_pem=device.get_private_key_pem_decrypted(),
            )
            sig_result = engine.sign(canonical)

            Receipt.objects.create(
                device=device,
                fiscal_day_no=1,
                receipt_global_no=global_no,
                receipt_counter=counter,
                currency="USD",
                receipt_taxes=taxes,
                receipt_type="FiscalInvoice",
                receipt_total=total_cents / 100,
                receipt_hash=expected_hash,
                receipt_signature_hash=sig_result["hash"],
                receipt_signature_sig=sig_result["signature"],
                receipt_date=timezone.make_aware(datetime(2025, 2, 11, 10, 30, 0)),
            )
            prev_hash = expected_hash

        result = validate_receipt_chain(device)
        self.assertFalse(result.has_errors)
        self.assertEqual(result.receipts_checked, 3)
        self.assertEqual(len(result.receipt_chain_errors), 0)
        self.assertEqual(len(result.receipt_hash_mismatches), 0)
        self.assertEqual(len(result.receipt_signature_failures), 0)

    def test_hash_mismatch_detected(self):
        """Stored hash != recalculated hash produces receipt_hash_mismatches."""
        device = _make_test_device()
        canonical = build_receipt_canonical_string(
            device_id=device.device_id,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-02-11T10:30:00",
            receipt_total=Decimal("15.00"),
            receipt_tax_lines=[],
            previous_receipt_hash=None,
        )
        wrong_hash = base64.b64encode(b"x" * 32).decode()
        Receipt.objects.create(
            device=device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_taxes=[],
            receipt_type="FiscalInvoice",
            receipt_total=15.00,
            receipt_hash=wrong_hash,
            receipt_signature_hash="",
            receipt_signature_sig="",
            receipt_date=timezone.make_aware(datetime(2025, 2, 11, 10, 30, 0)),
        )
        result = validate_receipt_chain(device)
        self.assertTrue(result.has_errors)
        self.assertEqual(len(result.receipt_hash_mismatches), 1)
        self.assertIn("Receipt 1", result.receipt_hash_mismatches[0])

    def test_chain_error_first_receipt_wrong_counter(self):
        """First receipt of day with receipt_counter != 1 produces chain error."""
        device = _make_test_device()
        canonical = build_receipt_canonical_string(
            device_id=device.device_id,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-02-11T10:30:00",
            receipt_total=Decimal("15.00"),
            receipt_tax_lines=[],
            previous_receipt_hash=None,
        )
        expected_hash = base64.b64encode(
            hashlib.sha256(canonical.encode("utf-8")).digest()
        ).decode()
        Receipt.objects.create(
            device=device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=2,  # Wrong: first of day should be 1
            currency="USD",
            receipt_taxes=[],
            receipt_type="FiscalInvoice",
            receipt_total=15.00,
            receipt_hash=expected_hash,
            receipt_signature_hash="",
            receipt_signature_sig="",
            receipt_date=timezone.make_aware(datetime(2025, 2, 11, 10, 30, 0)),
        )
        result = validate_receipt_chain(device)
        self.assertTrue(result.has_errors)
        self.assertEqual(len(result.receipt_chain_errors), 1)
        self.assertIn("got 2", result.receipt_chain_errors[0])
