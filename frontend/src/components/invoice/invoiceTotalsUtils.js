/**
 * Mirrors backend rounding: round each line subtotal, group by (tax_code, tax_pct),
 * then tax = round(subtotal * (1+pct/100), 2) - subtotal.
 * Uses tax from the selected tax (FDMS config) per line.
 */
function round2(val) {
  return Math.round(val * 100) / 100;
}

export function computeInvoiceTotals(items) {
  const taxByKey = {};
  let subtotal = 0;
  (items || []).forEach((it) => {
    const qty = parseFloat(it.quantity) || 0;
    const price = parseFloat(it.unit_price) || 0;
    const lineSubtotal = round2(qty * price);
    subtotal += lineSubtotal;
    const pct = Number.isNaN(parseFloat(it.tax_percent)) ? 0 : parseFloat(it.tax_percent);
    const taxCode = (it.tax_code || "").trim() || "VAT";
    const key = `${taxCode}|${pct}`;
    taxByKey[key] = (taxByKey[key] || 0) + lineSubtotal;
  });
  subtotal = round2(subtotal);
  let totalTax = 0;
  Object.entries(taxByKey).forEach(([key, amt]) => {
    const [, pctStr] = key.split("|");
    const pct = parseFloat(pctStr) || 0;
    const salesWithTax = round2(amt * (1 + pct / 100));
    totalTax += salesWithTax - amt;
  });
  totalTax = round2(totalTax);
  const grandTotal = round2(subtotal + totalTax);
  return { subtotal, totalTax, grandTotal, taxByKey };
}

export { round2 };
