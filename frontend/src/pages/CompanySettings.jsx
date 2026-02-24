import React, { useEffect, useState } from "react";
import axios from "axios";

function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  if (el) return el.getAttribute("content") || "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

export default function CompanySettings() {
  const [company, setCompany] = useState(null);
  const [form, setForm] = useState({
    name: "",
    tin: "",
    vat_number: "",
    address: "",
    phone: "",
    email: "",
    currency_default: "ZWL",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    axios
      .get("/api/company/", { withCredentials: true })
      .then((r) => {
        const c = r.data.company;
        setCompany(c);
        if (c) {
          setForm({
            name: c.name || "",
            tin: c.tin || "",
            vat_number: c.vat_number || "",
            address: c.address || "",
            phone: c.phone || "",
            email: c.email || "",
            currency_default: c.currency_default || "ZWL",
          });
        }
      })
      .catch(() => setMessage({ error: "Failed to load company" }))
      .finally(() => setLoading(false));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);
    setSaving(true);
    try {
      await axios.put("/api/company/", form, {
        withCredentials: true,
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "Content-Type": "application/json",
        },
      });
      setMessage({ success: true });
    } catch (err) {
      setMessage({
        error: err.response?.data?.error || err.message || "Failed to save",
      });
    } finally {
      setSaving(false);
    }
  };

  const update = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  if (loading) {
    return (
      <div className="max-w-2xl">
        <p className="text-slate-600">Loading...</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Company Settings</h1>
      <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Company Name</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            className="w-full border border-slate-300 rounded px-3 py-2"
            required
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">TIN</label>
            <input
              type="text"
              value={form.tin}
              onChange={(e) => update("tin", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">VAT Number</label>
            <input
              type="text"
              value={form.vat_number}
              onChange={(e) => update("vat_number", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Address</label>
          <textarea
            value={form.address}
            onChange={(e) => update("address", e.target.value)}
            rows={3}
            className="w-full border border-slate-300 rounded px-3 py-2"
            required
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">Phone</label>
            <input
              type="text"
              value={form.phone}
              onChange={(e) => update("phone", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => update("email", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
              required
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Default Currency</label>
          <select
            value={form.currency_default}
            onChange={(e) => update("currency_default", e.target.value)}
            className="w-full border border-slate-300 rounded px-3 py-2"
          >
            <option value="ZWL">ZWL</option>
            <option value="USD">USD</option>
          </select>
        </div>
        {message && (
          <div
            className={`p-4 rounded-lg ${message.error ? "bg-red-50 text-red-800" : "bg-green-50 text-green-800"}`}
          >
            {message.error || "Saved successfully"}
          </div>
        )}
        <button
          type="submit"
          disabled={saving}
          className="px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? "Saving..." : "Save"}
        </button>
      </form>
    </div>
  );
}
