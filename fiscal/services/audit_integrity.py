"""
Integrity & chain validation for fiscal data.
Rebuilds hashes, validates receipt chains, verifies signatures.
"""

import base64
import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from fiscal.models import FiscalDay, FiscalDevice, Receipt
from fiscal.services.receipt_engine import build_receipt_canonical_string

logger = logging.getLogger("fiscal")


def _to_cents(value) -> int:
    return int(
        (Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100)
        .to_integral_value()
    )


@dataclass
class AuditResult:
    """Results from integrity audit."""
    receipt_chain_errors: list[str] = field(default_factory=list)
    receipt_hash_mismatches: list[str] = field(default_factory=list)
    receipt_signature_failures: list[str] = field(default_factory=list)
    fiscal_day_counter_errors: list[str] = field(default_factory=list)
    devices_checked: int = 0
    receipts_checked: int = 0
    fiscal_days_checked: int = 0

    @property
    def has_errors(self) -> bool:
        return bool(
            self.receipt_chain_errors
            or self.receipt_hash_mismatches
            or self.receipt_signature_failures
            or self.fiscal_day_counter_errors
        )


def verify_receipt_signature(
    device: FiscalDevice,
    canonical: str,
    stored_hash_b64: str,
    stored_sig_b64: str,
) -> tuple[bool, str | None]:
    """
    Verify receipt signature using device certificate public key.
    Returns (True, None) if valid, (False, error_message) otherwise.
    """
    try:
        cert = x509.load_pem_x509_certificate(
            device.certificate_pem.encode() if isinstance(device.certificate_pem, str)
            else device.certificate_pem,
            default_backend(),
        )
        pub = cert.public_key()

        expected_hash = hashlib.sha256(canonical.encode("utf-8")).digest()
        stored_hash = base64.b64decode(stored_hash_b64)
        if expected_hash != stored_hash:
            return False, "Hash mismatch: recalculated hash != stored hash"

        sig_bytes = base64.b64decode(stored_sig_b64)

        if isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(sig_bytes, canonical.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        elif isinstance(pub, rsa.RSAPublicKey):
            pub.verify(
                sig_bytes,
                canonical.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        else:
            return False, "Unsupported key type"

        return True, None
    except Exception as e:
        return False, str(e)


def validate_receipt_chain(device: FiscalDevice) -> AuditResult:
    """
    Rebuild receipt chain, recalculate hashes, detect mismatches and broken chains.
    """
    result = AuditResult(devices_checked=1)
    receipts = (
        Receipt.objects.filter(device=device)
        .order_by("fiscal_day_no", "receipt_counter")
    )

    prev_hash_by_day: dict[int, str | None] = defaultdict(lambda: None)

    for rec in receipts:
        result.receipts_checked += 1

        receipt_date_str = ""
        if rec.receipt_date:
            receipt_date_str = rec.receipt_date.strftime("%Y-%m-%dT%H:%M:%S")
        receipt_total_dec = Decimal(str(rec.receipt_total or 0))

        prev_hash = prev_hash_by_day[rec.fiscal_day_no]

        canonical = build_receipt_canonical_string(
            device_id=device.device_id,
            receipt_type=rec.receipt_type or "FiscalInvoice",
            receipt_currency=rec.currency or "USD",
            receipt_global_no=rec.receipt_global_no,
            receipt_date=receipt_date_str,
            receipt_total=receipt_total_dec,
            receipt_tax_lines=rec.receipt_taxes or [],
            previous_receipt_hash=prev_hash,
        )

        expected_hash_b64 = base64.b64encode(
            hashlib.sha256(canonical.encode("utf-8")).digest()
        ).decode()

        if rec.receipt_hash and rec.receipt_hash != expected_hash_b64:
            result.receipt_hash_mismatches.append(
                f"Device {device.device_id} Receipt {rec.receipt_global_no} (day {rec.fiscal_day_no}): "
                f"stored hash != recalculated"
            )

        if rec.receipt_signature_hash and rec.receipt_signature_sig:
            ok, err = verify_receipt_signature(
                device=device,
                canonical=canonical,
                stored_hash_b64=rec.receipt_signature_hash,
                stored_sig_b64=rec.receipt_signature_sig,
            )
            if not ok:
                result.receipt_signature_failures.append(
                    f"Device {device.device_id} Receipt {rec.receipt_global_no}: {err}"
                )

        if prev_hash is None and rec.receipt_counter != 1:
            result.receipt_chain_errors.append(
                f"Device {device.device_id} Receipt {rec.receipt_global_no}: "
                f"first receipt of day should have receipt_counter=1, got {rec.receipt_counter}"
            )

        prev_hash_by_day[rec.fiscal_day_no] = expected_hash_b64

    return result


def rebuild_fiscal_day_counters(device: FiscalDevice, fiscal_day_no: int) -> tuple[list[dict], str | None]:
    """
    Rebuild fiscalDayCounters from receipts for a fiscal day.
    Returns (counters, None) or ([], error_message).
    """
    receipts = Receipt.objects.filter(
        device=device, fiscal_day_no=fiscal_day_no
    ).order_by("receipt_counter")

    if not receipts.exists():
        return [], None

    totals: dict[tuple, Decimal] = {}
    for rec in receipts:
        currency = rec.currency or "USD"
        for tax in rec.receipt_taxes or []:
            percent = tax.get("taxPercent", tax.get("fiscalCounterTaxPercent"))
            amount = tax.get("salesAmountWithTax", tax.get("fiscalCounterValue"))
            counter_type = tax.get("fiscalCounterType", tax.get("counterType", "saleByTax"))
            counter_type_lower = str(counter_type).lower()
            if counter_type_lower == "creditnotebytax":
                counter_type = "creditNoteByTax"
            elif counter_type_lower == "salebytax":
                counter_type = "saleByTax"
            else:
                counter_type = str(counter_type)
            if percent is None or amount is None:
                continue
            key = (counter_type, Decimal(str(percent)), currency)
            totals[key] = totals.get(key, Decimal("0")) + Decimal(str(amount))

    counters = []
    for (counter_type, percent, currency), value in totals.items():
        counters.append({
            "fiscalCounterType": counter_type,
            "fiscalCounterCurrency": currency,
            "fiscalCounterTaxPercent": round(float(percent), 2),
            "fiscalCounterValue": float(value.quantize(Decimal("0.01"), ROUND_HALF_UP)),
        })

    counters.sort(key=lambda x: (x["fiscalCounterTaxPercent"], x["fiscalCounterCurrency"]))
    return counters, None


def validate_fiscal_day_counters(device: FiscalDevice) -> AuditResult:
    """
    Rebuild fiscal day counters from receipts and validate consistency.
    """
    result = AuditResult(devices_checked=1)
    fiscal_days = FiscalDay.objects.filter(device=device).order_by("fiscal_day_no")

    for fd in fiscal_days:
        result.fiscal_days_checked += 1
        counters, err = rebuild_fiscal_day_counters(device, fd.fiscal_day_no)
        if err:
            result.fiscal_day_counter_errors.append(
                f"Device {device.device_id} FiscalDay {fd.fiscal_day_no}: {err}"
            )

    return result


def run_full_audit() -> AuditResult:
    """Run full integrity audit across all devices."""
    combined = AuditResult()
    devices = FiscalDevice.objects.filter(is_registered=True)

    for device in devices:
        combined.devices_checked += 1
        chain_result = validate_receipt_chain(device)
        combined.receipts_checked += chain_result.receipts_checked
        combined.receipt_chain_errors.extend(chain_result.receipt_chain_errors)
        combined.receipt_hash_mismatches.extend(chain_result.receipt_hash_mismatches)
        combined.receipt_signature_failures.extend(chain_result.receipt_signature_failures)

        counter_result = validate_fiscal_day_counters(device)
        combined.fiscal_days_checked += counter_result.fiscal_days_checked
        combined.fiscal_day_counter_errors.extend(counter_result.fiscal_day_counter_errors)

    return combined
