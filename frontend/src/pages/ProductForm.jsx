import React, { useEffect, useState } from "react";
import axios from "axios";

function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  if (el) return el.getAttribute("content") || "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

export default function ProductForm({ productId, onSaved, onCancel }) {
  const isEdit = !!productId;
  const [form, setForm] = useState({
    name: "",
    description: "",
    price: "0",
    tax_code: "VAT",
    tax_percent: "15",
    hs_code: "",
  });
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [taxOptions, setTaxOptions] = useState([]);

  useEffect(() => {
    axios.get("/api/config/taxes/", { withCredentials: true }).then((r) => {
      const taxes = r.data.taxes || [];
      setTaxOptions(taxes);
      if (taxes.length > 0 && !productId) {
        setForm((f) => ({ ...f, tax_code: taxes[0].taxCode, tax_percent: String(taxes[0].taxPercent) }));
      }
    }).catch(() => {
      setTaxOptions([{ taxCode: "VAT", taxPercent: 15, taxName: "VAT" }]);
    });
  }, [productId]);

  useEffect(() => {
    if (!productId) return;
    axios
      .get(`/api/products/${productId}/`, { withCredentials: true })
      .then((r) => {
        const p = r.data.product;
        setForm({
          name: p.name || "",
          description: p.description || "",
          price: String(p.price ?? 0),
          tax_code: p.tax_code || "VAT",
          tax_percent: String(p.tax_percent ?? 15),
          hs_code: p.hs_code || "",
        });
      })
      .catch(() => setMessage({ error: "Failed to load product" }))
      .finally(() => setLoading(false));
  }, [productId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        description: form.description,
        price: parseFloat(form.price) || 0,
        tax_code: form.tax_code,
        tax_percent: parseFloat(form.tax_percent) || 15,
        hs_code: form.hs_code,
      };
      if (isEdit) {
        await axios.put(`/api/products/${productId}/`, payload, {
          withCredentials: true,
          headers: { "X-CSRFToken": getCsrfToken(), "Content-Type": "application/json" },
        });
      } else {
        await axios.post("/api/products/", payload, {
          withCredentials: true,
          headers: { "X-CSRFToken": getCsrfToken(), "Content-Type": "application/json" },
        });
      }
      onSaved && onSaved();
    } catch (err) {
      setMessage({ error: err.response?.data?.error || err.message || "Failed to save" });
    } finally {
      setSaving(false);
    }
  };

  const update = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  if (loading) return <p className="text-slate-600">Loading...</p>;

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-indigo-600 hover:underline">
            ← Back
          </button>
        )}
        <h1 className="text-2xl font-bold text-slate-800">{isEdit ? "Edit Product" : "Add Product"}</h1>
      </div>
      <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 space-y-4 max-w-xl">
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Name *</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            className="w-full border border-slate-300 rounded px-3 py-2"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            rows={2}
            className="w-full border border-slate-300 rounded px-3 py-2"
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">Price *</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.price}
              onChange={(e) => update("price", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">Tax Code</label>
            <select
              value={form.tax_code}
              onChange={(e) => {
                const code = e.target.value;
                const t = taxOptions.find((o) => o.taxCode === code);
                setForm((f) => ({
                  ...f,
                  tax_code: code,
                  tax_percent: t ? String(t.taxPercent) : f.tax_percent,
                }));
              }}
              className="w-full border border-slate-300 rounded px-3 py-2"
            >
              {taxOptions.length === 0 && <option value={form.tax_code}>{form.tax_code}</option>}
              {taxOptions.map((t) => (
                <option key={t.taxCode} value={t.taxCode}>
                  {t.taxCode}{t.taxName !== t.taxCode ? ` (${t.taxName})` : ""} - {t.taxPercent}%
                </option>
              ))}
              {taxOptions.length > 0 && !taxOptions.some((t) => t.taxCode === form.tax_code) && (
                <option value={form.tax_code}>{form.tax_code} (custom)</option>
              )}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">Tax %</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.tax_percent}
              onChange={(e) => update("tax_percent", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">HS Code</label>
            <input
              type="text"
              value={form.hs_code}
              onChange={(e) => update("hs_code", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
              placeholder="e.g. 12345678"
            />
          </div>
        </div>
        {message && (
          <div className={`p-4 rounded-lg ${message.error ? "bg-red-50 text-red-800" : "bg-green-50 text-green-800"}`}>
            {message.error || "Saved"}
          </div>
        )}
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
          {onCancel && (
            <button type="button" onClick={onCancel} className="px-6 py-2 border border-slate-300 rounded hover:bg-slate-50">
              Cancel
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
