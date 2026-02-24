export default function InvoicePayments({ payments, setPayments, grandTotal }) {
  const addPayment = () => {
    setPayments([...payments, { method: "CASH", amount: 0 }]);
  };

  const removePayment = (i) => {
    setPayments(payments.filter((_, idx) => idx !== i));
  };

  const updatePayment = (i, field, value) => {
    const next = [...payments];
    next[i] = { ...next[i], [field]: value };
    setPayments(next);
  };

  const totalPaid = payments.reduce((s, p) => s + (parseFloat(p.amount) || 0), 0);
  const isValid = totalPaid >= grandTotal;

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4">
      <div className="flex justify-between items-center mb-3">
        <h2 className="font-semibold text-slate-800">Payments</h2>
        <button
          type="button"
          onClick={addPayment}
          className="text-indigo-600 hover:underline text-sm"
        >
          + Add payment
        </button>
      </div>
      <div className="space-y-2">
        {payments.map((p, i) => (
          <div key={i} className="flex gap-4 items-center">
            <select
              value={p.method || "CASH"}
              onChange={(e) => updatePayment(i, "method", e.target.value)}
              className="border border-slate-300 rounded px-2 py-1"
            >
              <option value="CASH">CASH</option>
              <option value="CARD">CARD</option>
              <option value="MOBILE">MOBILE</option>
              <option value="ECOCASH">ECOCASH</option>
              <option value="BANK_TRANSFER">BANK_TRANSFER</option>
            </select>
            <input
              type="number"
              min="0"
              step="0.01"
              value={p.amount ?? 0}
              onChange={(e) => updatePayment(i, "amount", parseFloat(e.target.value) || 0)}
              placeholder="Amount"
              className="border border-slate-300 rounded px-2 py-1 w-32"
            />
            <button
              type="button"
              onClick={() => removePayment(i)}
              className="text-red-600 hover:underline text-sm"
            >
              Remove
            </button>
          </div>
        ))}
      </div>
      <p className={`mt-2 text-sm ${isValid ? "text-green-600" : "text-amber-600"}`}>
        Total paid: {totalPaid.toFixed(2)} {isValid ? "✓" : `(need ${(grandTotal - totalPaid).toFixed(2)} more)`}
      </p>
    </div>
  );
}
