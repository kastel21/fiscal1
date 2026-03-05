"""
Robust Excel Invoice importer. Detects header row and buyer info, extracts line items,
returns structured data for the New Invoice form only. Does NOT create receipts or call FDMS.
"""

import io
import re

import pandas as pd

# Quotation sheet format: Qty, Item Number, Description, Unit Price or Amount Due, etc.
QUOTATION_REQUIRED = ("qty", "item_number", "description", "unit_price")
QUOTATION_UNIT_PRICE_ALIASES = ("unit_price", "amount_due")
DEFAULT_TAX_RATE = 15.5

HEADER_ALIASES = {
    "code": ["code", "item_code", "product_code", "item_number"],
    "description": ["description", "item", "product"],
    "qty": ["qty", "quantity"],
    "unit_price": ["unit_price", "price", "unit price"],
    "tax_rate": ["tax_rate", "vat", "tax", "vat_rate"],
}
BUYER_KEYS = ("buyer_name", "buyer_tin", "buyer_vat", "reference", "currency", "buyer_address")
# Common Excel labels that map to buyer keys (normalized: lowercase, spaces -> underscores)
BUYER_KEY_ALIASES = {
    "buyer_name": ["customer_name", "company_name", "client", "client_name", "customer", "buyer", "name", "company"],
    "buyer_tin": ["tin", "tax_id", "tax_number", "tax_no", "vat_registration_no"],
    "buyer_vat": ["vat", "vat_number", "vat_no", "buyer_vat"],
    "reference": ["reference", "ref", "invoice_reference", "ref_no"],
    "currency": ["currency", "curr"],
    "buyer_address": ["address", "street", "physical_address", "delivery_address"],
}
REQUIRED_COLUMNS = ("code", "description", "qty", "unit_price", "tax_rate")
EXEMPT_VALUES = ("exempt", "0", "0%", "n/a", "-")


class InvoiceImportError(Exception):
    """Raised when Excel is invalid or validation fails."""
    pass


def normalize(value):
    """Convert to string, lowercase, strip, replace spaces with underscores."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _find_invoice_sheet(sheet_names: list) -> str | None:
    """Return the first sheet whose name starts with 'invoice' (case-insensitive). Only this sheet is ever used."""
    for name in sheet_names or []:
        if str(name).strip().lower().startswith("invoice"):
            return name
    return None


def detect_vat_rate(df: pd.DataFrame) -> float:
    """
    Scan the entire sheet for the word 'VAT' and extract a numeric rate from the same cell.
    Handles patterns like 'VAT 15.5%', 'VAT: 15.5', 'VAT (15.5%)'. Returns 15.5 if not found.
    """
    for _, row in df.iterrows():
        for cell in row:
            if pd.isna(cell):
                continue
            s = cell if isinstance(cell, str) else str(cell)
            if "vat" in s.lower():
                match = re.search(r"(\d+(?:\.\d+)?)", s)
                if match:
                    return float(match.group(1))
    return DEFAULT_TAX_RATE


def _detect_quotation_header_row(df: pd.DataFrame) -> int:
    """Find row containing ALL of: Qty, Item Number, Description, and Unit Price or Amount Due. Return -1 if not found."""
    required = set(QUOTATION_REQUIRED)
    for idx in range(min(30, len(df))):
        row = df.iloc[idx]
        cells = [normalize(row.iloc[i]) for i in range(min(20, len(row))) if pd.notna(row.iloc[i])]
        cell_set = set(cells)
        if "amount_due" in cell_set and "unit_price" not in cell_set:
            cell_set.add("unit_price")
        if required.issubset(cell_set):
            return idx
    return -1


def _parse_quotation_sheet(xl, sheet_name: str) -> dict:
    """Parse quotation format: Qty, Item Number, Description, Unit Price; tax_rate from sheet or 15.5."""
    df_raw = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    if df_raw.empty or len(df_raw) < 2:
        raise InvoiceImportError(f'Sheet "{sheet_name}" is empty or has no data.')
    tax_rate = detect_vat_rate(df_raw)
    header_row_idx = _detect_quotation_header_row(df_raw)
    if header_row_idx < 0:
        raise InvoiceImportError(
            'Could not find header row containing: Qty, Item Number, Description, Unit Price.'
        )
    df = pd.read_excel(xl, sheet_name=sheet_name, header=header_row_idx)
    col_by_norm = {}
    for c in df.columns:
        n = normalize(c)
        if n:
            col_by_norm[n] = c
        if n in QUOTATION_UNIT_PRICE_ALIASES:
            col_by_norm["unit_price"] = c
    missing = [k for k in QUOTATION_REQUIRED if k not in col_by_norm]
    if missing:
        raise InvoiceImportError(f"Quotation sheet missing columns: {', '.join(missing)}.")
    items = []
    for _, row in df.iterrows():
        code_val = row.get(col_by_norm["item_number"])
        if pd.isna(code_val) or str(code_val).strip() == "":
            continue
        try:
            qty = float(row[col_by_norm["qty"]]) if pd.notna(row[col_by_norm["qty"]]) else 1
        except (TypeError, ValueError):
            qty = 1
        try:
            unit_price = float(row[col_by_norm["unit_price"]]) if pd.notna(row[col_by_norm["unit_price"]]) else 0
        except (TypeError, ValueError):
            unit_price = 0
        if qty <= 0 or unit_price < 0:
            continue
        items.append({
            "code": str(code_val).strip(),
            "description": str(row.get(col_by_norm["description"], "") or "").strip(),
            "quantity": qty,
            "unit_price": round(unit_price, 2),
            "tax_rate": str(tax_rate),
        })
    if not items:
        raise InvoiceImportError("No valid line items found (Item Number non-empty, Qty > 0, Unit Price >= 0).")
    buyer = _detect_buyer_info(df_raw)
    if not buyer.get("currency"):
        buyer["currency"] = "USD"
    return {"buyer": buyer, "items": items}


def _key_to_buyer_field(norm_key: str) -> str | None:
    """Map normalized label (e.g. 'customer_name') to buyer key (e.g. 'buyer_name')."""
    if norm_key in BUYER_KEYS:
        return norm_key
    for buyer_key, aliases in BUYER_KEY_ALIASES.items():
        if norm_key in aliases:
            return buyer_key
    return None


def _find_to_section(df: pd.DataFrame) -> tuple[int, int] | None:
    """Find a cell containing 'To:' (case-insensitive). Return (row_idx, col_idx) or None."""
    for idx in range(min(50, len(df))):
        row = df.iloc[idx]
        for c in range(min(20, len(row))):
            cell = row.iloc[c] if c < len(row) else None
            if pd.isna(cell):
                continue
            s = str(cell).strip().lower()
            if s == "to:" or s == "to" or (s.startswith("to:") and len(s) <= 6):
                return (idx, c)
            if "to:" in s:
                return (idx, c)
    return None


def _detect_buyer_info_under_to(df: pd.DataFrame) -> dict:
    """Extract all customer info between 'To:' and 'Att:': name, key-value fields, and remaining lines as address."""
    out = {k: "" for k in BUYER_KEYS}
    found = _find_to_section(df)
    if not found:
        return out
    start_row, start_col = found
    # Buyer name: cell to the right of "To:" or first cell in the row below
    if start_col + 1 < df.shape[1]:
        cell = df.iloc[start_row].iloc[start_col + 1]
        if not pd.isna(cell) and str(cell).strip():
            out["buyer_name"] = str(cell).strip()
    if not out["buyer_name"] and start_row + 1 < len(df):
        row = df.iloc[start_row + 1]
        if start_col < len(row):
            cell = row.iloc[start_col]
            if not pd.isna(cell) and str(cell).strip():
                out["buyer_name"] = str(cell).strip()
    # Collect all rows between To: and Att:; split into key-value pairs and address lines
    address_lines = []
    for idx in range(start_row + 1, min(start_row + 25, len(df))):
        row = df.iloc[idx]
        hit_att = False
        for c in range(len(row)):
            cell = row.iloc[c] if c < len(row) else None
            if pd.isna(cell):
                continue
            s = str(cell).strip().lower()
            if s.startswith("att:") or s == "att" or s == "att":
                hit_att = True
                break
        if hit_att:
            break
        if start_col >= len(row):
            continue
        key_cell = row.iloc[start_col]
        key = normalize(key_cell)
        val = ""
        if start_col + 1 < len(row) and pd.notna(row.iloc[start_col + 1]):
            val = str(row.iloc[start_col + 1]).strip()
        field = _key_to_buyer_field(key) if key else None
        if field:
            if val:
                out[field] = val
        else:
            # Not a recognized key: treat as address line (value column, or first column if no value)
            if val:
                address_lines.append(val)
            elif key:
                address_lines.append(str(key_cell).strip() if not pd.isna(key_cell) else "")
    if address_lines:
        out["buyer_address"] = "\n".join(ln for ln in address_lines if ln)
    if out.get("currency"):
        out["currency"] = (out["currency"] or "USD").strip().upper() or "USD"
    return out


def _detect_buyer_info(df: pd.DataFrame) -> dict:
    """First try 'To:' section; then scan first rows as col0=label, col1=value. Merge results."""
    out = {k: "" for k in BUYER_KEYS}
    from_to = _detect_buyer_info_under_to(df)
    for k in BUYER_KEYS:
        if from_to.get(k):
            out[k] = from_to[k]
    for idx in range(min(30, len(df))):
        row = df.iloc[idx]
        if len(row) < 2:
            continue
        key = normalize(row.iloc[0])
        val = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
        field = _key_to_buyer_field(key)
        if field and not out[field]:
            out[field] = val
    if out.get("currency"):
        out["currency"] = (out["currency"] or "USD").strip().upper() or "USD"
    return out


def _detect_header_row(df: pd.DataFrame) -> int:
    """Find row index where at least 3 expected columns (via aliases) appear. Return -1 if not found."""
    for idx in range(min(30, len(df))):
        row = df.iloc[idx]
        cells = [normalize(row.iloc[i]) if i < len(row) and pd.notna(row.iloc[i]) else "" for i in range(20)]
        matches = 0
        for sys_col, aliases in HEADER_ALIASES.items():
            if any(norm in (sys_col,) + tuple(aliases) for norm in cells if norm):
                matches += 1
        if matches >= 3:
            return idx
    return -1


def map_columns(header_row) -> dict:
    """
    Map system column names to 0-based column indices using HEADER_ALIASES.
    header_row: pandas Series or list of cell values.
    Returns dict: system_name -> column_index (e.g. "code" -> 0).
    Raises InvoiceImportError if required columns missing.
    """
    result = {}
    n = len(header_row)
    for i in range(n):
        cell = header_row.iloc[i] if hasattr(header_row, "iloc") else header_row[i]
        norm = normalize(cell)
        if not norm:
            continue
        for sys_col, aliases in HEADER_ALIASES.items():
            if sys_col in result:
                continue
            if norm == sys_col or norm in aliases:
                result[sys_col] = i
                break
    missing = [c for c in REQUIRED_COLUMNS if c not in result]
    if missing:
        raise InvoiceImportError(f"Missing required columns: {', '.join(missing)}. Found: {list(header_row)[:15]}")
    return result


def _normalize_tax_rate(value) -> str:
    s = normalize(value)
    if not s or s in EXEMPT_VALUES:
        return "EXEMPT"
    s = s.rstrip("%")
    if s in ("exempt", "n/a", "-"):
        return "EXEMPT"
    try:
        n = float(s)
        if n < 0:
            raise InvoiceImportError(f"tax_rate must be >= 0 or EXEMPT, got: {value}")
        return str(n)
    except ValueError:
        raise InvoiceImportError(f"Invalid tax_rate: {value}. Use a number or EXEMPT.")


def load_invoice_review(file) -> dict:
    """
    Parse Excel: always use the sheet whose name starts with "Invoice" (case-insensitive).
    Detect buyer info, header row, map columns, extract and validate items.
    Returns {"buyer": {...}, "items": [...]}. Does NOT create receipt or call FDMS.
    """
    if hasattr(file, "read"):
        content = file.read()
        file = io.BytesIO(content) if isinstance(content, bytes) else io.BytesIO(content.encode("utf-8"))
    try:
        xl = pd.ExcelFile(file, engine="openpyxl")
    except Exception as e:
        raise InvoiceImportError(f"Cannot read Excel: {e}") from e

    # Always use the sheet whose name starts with "Invoice"; ignore all other sheets
    sheet_name = _find_invoice_sheet(xl.sheet_names)
    if not sheet_name:
        raise InvoiceImportError(f'No sheet starting with "Invoice" found. Found: {", ".join(xl.sheet_names)}.')

    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    if df.empty or len(df) < 2:
        raise InvoiceImportError(f'Sheet "{sheet_name}" is empty or has no data.')

    if _detect_quotation_header_row(df) >= 0:
        return _parse_quotation_sheet(xl, sheet_name)

    buyer = _detect_buyer_info(df)
    buyer.setdefault("currency", (buyer.get("currency") or "USD").strip().upper() or "USD")

    header_row_idx = _detect_header_row(df)
    if header_row_idx < 0:
        raise InvoiceImportError('Could not detect header row (need code, description, qty, unit_price, tax_rate).')

    header_row = df.iloc[header_row_idx]
    col_idx = map_columns(header_row)

    items = []
    for r in range(header_row_idx + 1, len(df)):
        row = df.iloc[r]
        code = str(row.iloc[col_idx["code"]]).strip() if col_idx["code"] < len(row) else ""
        if not code:
            continue
        description = str(row.iloc[col_idx["description"]]).strip() if col_idx["description"] < len(row) else ""
        try:
            qty = float(row.iloc[col_idx["qty"]]) if col_idx["qty"] < len(row) else 1
        except (TypeError, ValueError):
            qty = 1
        try:
            unit_price = float(row.iloc[col_idx["unit_price"]]) if col_idx["unit_price"] < len(row) else 0
        except (TypeError, ValueError):
            unit_price = 0
        if qty <= 0 or unit_price < 0:
            continue
        tax_raw = row.iloc[col_idx["tax_rate"]] if col_idx["tax_rate"] < len(row) else None
        tax_rate = _normalize_tax_rate(tax_raw)
        item = {"code": code, "description": description, "quantity": qty, "unit_price": round(unit_price, 2), "tax_rate": tax_rate}
        items.append(item)

    if not items:
        raise InvoiceImportError("No valid line items (code non-empty, quantity > 0, unit_price >= 0).")

    return {"buyer": buyer, "items": items}
