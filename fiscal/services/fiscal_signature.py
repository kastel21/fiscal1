"""
Fiscal day signature generation for CloseDay.
SHA256 hash + ECC/RSA sign with device private key, Base64 encode.

Canonical string per FDMS spec section 13.3.1.
"""

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fiscal.services.signature_engine import SignatureEngine

logger = logging.getLogger("fiscal")


def build_fiscal_day_canonical_string(
    device_id: int,
    fiscal_day_no: int,
    fiscal_day_date: date,
    fiscal_day_counters: list[dict],
) -> str:
    """
    Build fiscal day canonical string according to FDMS spec section 13.3.1.

    Order:
        1. deviceID
        2. fiscalDayNo
        3. fiscalDayDate (YYYY-MM-DD)
        4. fiscalDayCounters (concatenated, no separator)

    Rules:
        - No concatenation character
        - Only non-zero counters included
        - All text upper case
        - Amounts in cents
        - Sorted as specified in spec
    """

    # 1 + 2 + 3
    canonical = (
        str(device_id)
        + str(fiscal_day_no)
        + fiscal_day_date.strftime("%Y-%m-%d")
    )

    if not fiscal_day_counters:
        return canonical

    # Filter only non-zero counters
    non_zero_counters = [
        c for c in fiscal_day_counters
        if Decimal(str(c.get("fiscalCounterValue", 0))) != Decimal("0")
    ]

    if not non_zero_counters:
        return canonical

    def to_cents(value) -> str:
        """Convert monetary value to cents as string."""
        return str(
            (Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100)
            .to_integral_value()
        )

    def format_tax_percent(value) -> str:
        """
        Format tax percent according to spec:
        - If integer → 15.00
        - If decimal → 14.50
        - If empty (exempt) → empty string
        """
        if value is None or value == "":
            return ""

        dec = Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return f"{dec:.2f}"

    # Sort counters: type in fixed order (saleByTax, saleTaxByTax, then balanceByMoneyType, then others),
    # then fiscalCounterCurrency (ascending), then tax percent or money type (ascending).
    # Canonical example: ...SALEBYTAXUSD15.50300SALETAXBYTAXUSD15.5047BALANCEBYMONEYTYPEUSDCASH347
    _TYPE_ORDER = (
        "SALEBYTAX",
        "SALETAXBYTAX",
        "CREDITNOTEBYTAX",
        "CREDITNOTETAXBYTAX",
        "DEBITNOTEBYTAX",
        "DEBITNOTETAXBYTAX",
        "BALANCEBYMONEYTYPE",
    )

    def counter_sort_key(c: dict):
        ctype = str(c.get("fiscalCounterType", "")).upper()
        try:
            type_rank = _TYPE_ORDER.index(ctype)
        except ValueError:
            type_rank = 999
        third = (
            c.get("fiscalCounterTaxID")
            or c.get("fiscalCounterMoneyType")
        )
        if third is None and c.get("fiscalCounterTaxPercent") is not None:
            third = format_tax_percent(c.get("fiscalCounterTaxPercent"))
        return (
            type_rank,
            str(c.get("fiscalCounterCurrency", "")).upper(),
            str(third or "").upper(),
        )

    sorted_counters = sorted(non_zero_counters, key=counter_sort_key)

    for counter in sorted_counters:
        counter_type = str(counter.get("fiscalCounterType", "")).upper()
        currency = str(counter.get("fiscalCounterCurrency", "")).upper()

        # Either taxPercent OR moneyType. For tax ID 1 (Exempt) do not include percent.
        tax_id = counter.get("fiscalCounterTaxID")
        tax_percent = counter.get("fiscalCounterTaxPercent")
        money_type = counter.get("fiscalCounterMoneyType")

        if tax_id == 1:
            percent_or_money = ""
        elif tax_percent is not None:
            percent_or_money = format_tax_percent(tax_percent)
        else:
            percent_or_money = str(money_type or "").upper()

        value_cents = to_cents(counter.get("fiscalCounterValue", 0))

        canonical += (
            counter_type
            + currency
            + percent_or_money
            + value_cents
        )

    return canonical


def sign_fiscal_day_report(
    device_id: int,
    fiscal_day_no: int,
    fiscal_day_date: date,
    fiscal_day_counters: list[dict],
    private_key_pem: str | bytes,
    certificate_pem: str | bytes,
) -> dict:
    """
    Generate fiscalDayDeviceSignature for CloseDay request.

    1. Build canonical string per FDMS spec 13.3.1
    2. SHA256 hash → base64
    3. Sign canonical string with private key → base64
    4. Return {"hash": ..., "signature": ...}
    """
    canonical = build_fiscal_day_canonical_string(
        device_id=device_id,
        fiscal_day_no=fiscal_day_no,
        fiscal_day_date=fiscal_day_date,
        fiscal_day_counters=fiscal_day_counters,
    )

    engine = SignatureEngine(certificate_pem=certificate_pem, private_key_pem=private_key_pem)
    result = engine.sign(canonical)

    logger.info(
        "CloseDay signature — algo: %s, canonical: %r, hash: %s",
        engine.detect_algorithm(),
        canonical,
        result["hash"],
    )
    return result
