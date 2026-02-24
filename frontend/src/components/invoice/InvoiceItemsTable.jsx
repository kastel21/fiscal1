const INVOICE_TAXES = [
  { taxID: 1, taxPercent: 0, taxCode: "1", name: "0% (1)" },
  { taxID: 2, taxPercent: 0, taxCode: "2", name: "0% (2)" },
  { taxID: 517, taxPercent: 15.5, taxCode: "517", name: "15.5%" },
];

export default function InvoiceItemsTable({ items, setItems, isVatRegistered = true }) {
  const taxes = isVatRegistered
    ? INVOICE_TAXES
    : INVOICE_TAXES.filter((t) => t.taxPercent === 0);

  const addItem = () => {
    setItems([
      ...items,
      {
        description: "",
        quantity: 1,
        unit_price: 0,
        tax_id: taxes[0]?.taxID ?? null,
        tax_percent: taxes[0] ? parseFloat(taxes[0].taxPercent) : 0,
        tax_code: taxes[0]?.taxCode || taxes[0]?.taxName || "VAT",
        hs_code: "",
      },
    ]);
  };

  const removeItem = (i) => {
    setItems(items.filter((_, idx) => idx !== i));
  };

  const updateItem = (i, field, value) => {
    const updated = [...items];
    updated[i] = { ...updated[i], [field]: value };
    const it = updated[i];

    if (field === "tax_id" && value !== null && value !== undefined && value !== "") {
      const selTax = taxes.find((x) => x.taxID === Number(value));
      if (selTax) {
        it.tax_percent = parseFloat(selTax.taxPercent);
        it.tax_code = selTax.taxCode;
      }
    }

    if (["quantity", "unit_price", "tax_id"].includes(field)) {
      const qty = parseFloat(it.quantity) || 0;
      const price = parseFloat(it.unit_price) || 0;
      const lineSub = Math.round(qty * price * 100) / 100;
      const pct = Number.isNaN(parseFloat(it.tax_percent)) ? 0 : parseFloat(it.tax_percent);
      it.line_total = Math.round(lineSub * (1 + pct / 100) * 100) / 100;
    }

    setItems(updated);
  };

  return (
    <div className="bg-white shadow rounded-xl p-4">
      <h3 className="font-semibold mb-3">Items</h3>
      {!isVatRegistered && (
        <p className="text-amber-600 text-sm mb-2">Device not VAT registered. Only 0% tax available.</p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th>Item Name</th>
            <th>Qty</th>
            <th>Unit Price</th>
            <th>Tax</th>
            <th>HS Code</th>
            <th>Total</th>
            <th></th>
          </tr>
        </thead>

        <tbody>
          {items.map((item, index) => {
            const qty = parseFloat(item.quantity) || 0;
            const price = parseFloat(item.unit_price) || 0;
            const lineSub = Math.round(qty * price * 100) / 100;
            const pct = Number.isNaN(parseFloat(item.tax_percent)) ? 0 : parseFloat(item.tax_percent);
            const lineTotal = Math.round(lineSub * (1 + pct / 100) * 100) / 100;
            return (
              <tr key={index} className="border-b">
                <td>
                  <input
                    type="text"
                    value={item.description || ""}
                    onChange={(e) => updateItem(index, "description", e.target.value)}
                    placeholder="Item description"
                    className="border p-1 rounded w-full"
                  />
                </td>

                <td>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={item.quantity ?? 1}
                    onChange={(e) => updateItem(index, "quantity", parseFloat(e.target.value) || 0)}
                    className="border p-1 rounded w-20"
                  />
                </td>

                <td>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={item.unit_price ?? 0}
                    onChange={(e) => updateItem(index, "unit_price", parseFloat(e.target.value) || 0)}
                    className="border p-1 rounded w-24"
                  />
                </td>

                <td>
                  <select
                    value={item.tax_id ?? ""}
                    onChange={(e) => updateItem(index, "tax_id", e.target.value ? Number(e.target.value) : null)}
                    className="border p-1 rounded w-full min-w-[100px]"
                  >
                    <option value="">Select tax</option>
                    {taxes.map((t) => (
                      <option key={t.taxID} value={t.taxID}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </td>

                <td>
                  <input
                    type="text"
                    value={item.hs_code || ""}
                    onChange={(e) => updateItem(index, "hs_code", e.target.value)}
                    placeholder="e.g. 000000"
                    className="border p-1 rounded w-24"
                  />
                </td>

                <td>{lineTotal.toFixed(2)}</td>

                <td>
                  <button
                    type="button"
                    className="text-red-500"
                    onClick={() => removeItem(index)}
                  >
                    X
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <button
        type="button"
        onClick={addItem}
        className="mt-3 bg-blue-600 text-white px-3 py-1 rounded"
      >
        Add Item
      </button>
    </div>
  );
}
