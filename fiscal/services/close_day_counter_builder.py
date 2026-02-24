"""
CloseDay counter aggregation per FDMS spec.
- FISCALINVOICE: SaleByTax, SaleTaxByTax, BalanceByMoneyType
- CREDITNOTE: CreditNoteByTax, CreditNoteTaxByTax (abs only), BalanceByMoneyType
- DEBITNOTE: DebitNoteByTax, DebitNoteTaxByTax, BalanceByMoneyType
Do NOT net. Only abs() for CreditNote tax counters. BalanceByMoneyType uses signed paymentAmount.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from fiscal.models import FiscalDevice, Receipt

# Map payment method/moneyTypeCode to canonical format for BALANCEBYMONEYTYPEUSDCASH (FDMS spec)
_CLOSE_DAY_MONEY_TYPE_MAP = {
    "CASH": "CASH",
    "CARD": "CARD",
    "MOBILE": "CARD",
    "MOBILEWALLET": "CARD",
    "ECOCASH": "CARD",
    "BANK_TRANSFER": "CARD",
    "BANKTRANSFER": "CARD",
    "COUPON": "CARD",
    "CREDIT": "CARD",
    "OTHER": "CARD",
}


def get_day_receipts(device: FiscalDevice, fiscal_day_no: int):
    """Fetch all fiscalised receipts for the fiscal day."""
    return Receipt.objects.filter(
        device=device,
        fiscal_day_no=fiscal_day_no,
    ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0)


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _round2(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_fiscal_day_counters(receipts) -> dict:
    """
    Aggregate counters by receipt type. Do NOT net invoices and credits.
    Returns dict: key = (counter_type, currency, tax_id_or_money, tax_pct_or_none), value = Decimal.
    """
    counters: dict[tuple, Decimal] = defaultdict(Decimal)

    for receipt in receipts:
        currency = (receipt.currency or "USD").strip().upper()
        rt = (receipt.receipt_type or "").strip().upper()
        if rt in ("FISCALINVOICE", "FISCALRECEIPT", ""):
            counter_sales = "SaleByTax"
            counter_tax = "SaleTaxByTax"
        elif rt in ("CREDITNOTE",):
            counter_sales = "CreditNoteByTax"
            counter_tax = "CreditNoteTaxByTax"
        elif rt in ("DEBITNOTE",):
            counter_sales = "DebitNoteByTax"
            counter_tax = "DebitNoteTaxByTax"
        else:
            continue

        for tax in receipt.receipt_taxes or []:
            tax_id = tax.get("taxID")
            if tax_id is not None:
                tax_id = int(tax_id)
            else:
                tax_id = 1
            percent = tax.get("taxPercent", tax.get("fiscalCounterTaxPercent"))
            if percent is None:
                continue
            pct = round(float(percent), 2)
            sales_with_tax = _to_decimal(tax.get("salesAmountWithTax", tax.get("fiscalCounterValue")) or 0)
            tax_amt = _to_decimal(tax.get("taxAmount") or 0)

            if rt in ("CREDITNOTE",):
                sales_with_tax = sales_with_tax
                tax_amt = tax_amt

            key_sales = (counter_sales, currency, tax_id, pct)
            key_tax = (counter_tax, currency, tax_id, pct)
            counters[key_sales] += sales_with_tax
            counters[key_tax] += tax_amt

        for pay in receipt.receipt_payments or []:
            amt = _to_decimal(pay.get("paymentAmount", pay.get("amount")) or 0)
            method = str(
                pay.get("moneyTypeCode") or pay.get("moneyType") or pay.get("method") or "CASH"
            ).strip().upper()
            money_type = _CLOSE_DAY_MONEY_TYPE_MAP.get(method, "CASH")
            key = ("BalanceByMoneyType", currency, money_type, None)
            counters[key] += amt

    return counters


def convert_to_fdms_format(counter_dict: dict) -> list[dict]:
    """Convert counter dict to FDMS fiscalDayCounters format."""
    fiscal_day_counters = []
    for key, value in counter_dict.items():
        if value == 0:
            continue
        counter_type = key[0]
        currency = key[1]
        if counter_type == "BalanceByMoneyType":
            _, _, money_type, _ = key
            fiscal_day_counters.append({
                "fiscalCounterType": counter_type,
                "fiscalCounterCurrency": currency,
                "fiscalCounterMoneyType": money_type,
                "fiscalCounterValue": _round2(value),
            })
        else:
            _, _, tax_id, tax_percent = key
            item = {
                "fiscalCounterType": counter_type,
                "fiscalCounterCurrency": currency,
                "fiscalCounterTaxID": tax_id,
                "fiscalCounterValue": _round2(value),
            }
            if tax_id != 1:
                item["fiscalCounterTaxPercent"] = tax_percent
            fiscal_day_counters.append(item)
    return fiscal_day_counters


def sort_fiscal_counters(counters: list[dict]) -> list[dict]:
    """Sort counters per FDMS/fiscal_signature rules: type, currency, taxID/moneyType."""
    _TYPE_ORDER = (
        "SALEBYTAX",
        "SALETAXBYTAX",
        "CREDITNOTEBYTAX",
        "CREDITNOTETAXBYTAX",
        "DEBITNOTEBYTAX",
        "DEBITNOTETAXBYTAX",
        "BALANCEBYMONEYTYPE",
    )

    def sort_key(item: dict):
        ctype = str(item.get("fiscalCounterType", "")).upper()
        try:
            type_rank = _TYPE_ORDER.index(ctype)
        except ValueError:
            type_rank = 999
        curr = str(item.get("fiscalCounterCurrency", "")).upper()
        third = item.get("fiscalCounterTaxID") or item.get("fiscalCounterMoneyType")
        if third is None and item.get("fiscalCounterTaxPercent") is not None:
            third = item.get("fiscalCounterTaxPercent")
        return (type_rank, curr, str(third or "").upper())

    return sorted(counters, key=sort_key)


def build_close_day_counters(device: FiscalDevice, fiscal_day_no: int) -> list[dict]:
    """
    Build FDMS fiscalDayCounters from receipts for the fiscal day.
    Separate counters for Sale, CreditNote, DebitNote. Do NOT net.
    """
    receipts = get_day_receipts(device, fiscal_day_no)
    counter_dict = build_fiscal_day_counters(receipts)
    fdms_counters = convert_to_fdms_format(counter_dict)
    return sort_fiscal_counters(fdms_counters)
