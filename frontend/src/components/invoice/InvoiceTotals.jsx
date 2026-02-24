import { computeInvoiceTotals, round2 } from "./invoiceTotalsUtils";

export default function InvoiceTotals({ items = [] }) {
  const { subtotal, totalTax, grandTotal, taxByKey } = computeInvoiceTotals(items);

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4">
      <h2 className="font-semibold text-slate-800 mb-3">Totals</h2>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-slate-600">Subtotal</span>
          <span>{subtotal.toFixed(2)}</span>
        </div>
        {Object.entries(taxByKey).map(([key, amt]) => {
          const [, pctStr] = key.split("|");
          const pct = parseFloat(pctStr) || 0;
          const salesWithTax = round2(amt * (1 + pct / 100));
          const taxAmt = salesWithTax - amt;
          return (
            <div key={key} className="flex justify-between text-slate-600">
              <span>Tax {pct}%</span>
              <span>{taxAmt.toFixed(2)}</span>
            </div>
          );
        })}
        <div className="flex justify-between text-slate-600">
          <span>Total Tax</span>
          <span>{totalTax.toFixed(2)}</span>
        </div>
        <div className="flex justify-between font-bold text-slate-800 pt-2 border-t">
          <span>Grand Total</span>
          <span>{grandTotal.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
