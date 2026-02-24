"""
FDMS receipt type mapping for document types. Mapping layer only; does not change submit logic.
"""


def get_fdms_receipt_type(document_type: str) -> str:
    """
    Map business document_type to FDMS receiptType.
    CREDIT_NOTE -> CreditNote (fiscal credit receipt).
    INVOICE / DEBIT_NOTE -> FISCALINVOICE (normal fiscal receipt).
    """
    if document_type == "CREDIT_NOTE":
        return "CreditNote"
    return "FISCALINVOICE"
