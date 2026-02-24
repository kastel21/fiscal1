import React, { useEffect, useState } from "react";
import axios from "axios";

function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  if (el) return el.getAttribute("content") || "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

export default function CustomerForm({ customerId, onSaved, onCancel }) {
  const isEdit = !!customerId;
  const [form, setForm] = useState({
    name: "",
    tin: "",
    address: "",
    phone: "",
    email: "",
  });
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!customerId) return;
    axios
      .get(`/api/customers/${customerId}/`, { withCredentials: true })
      .then((r) => {
        const c = r.data.customer;
        setForm({
          name: c.name || "",
          tin: c.tin || "",
          address: c.address || "",
          phone: c.phone || "",
          email: c.email || "",
        });
      })
      .catch(() => setMessage({ error: "Failed to load customer" }))
      .finally(() => setLoading(false));
  }, [customerId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        tin: form.tin.trim(),
        address: form.address.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
      };
      if (isEdit) {
        await axios.put(`/api/customers/${customerId}/`, payload, {
          withCredentials: true,
          headers: { "X-CSRFToken": getCsrfToken(), "Content-Type": "application/json" },
        });
      } else {
        await axios.post("/api/customers/", payload, {
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
        <h1 className="text-2xl font-bold text-slate-800">{isEdit ? "Edit Customer" : "Add Customer"}</h1>
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
          <label className="block text-sm font-medium text-slate-600 mb-1">TIN</label>
          <input
            type="text"
            value={form.tin}
            onChange={(e) => update("tin", e.target.value)}
            placeholder="Tax ID"
            className="w-full border border-slate-300 rounded px-3 py-2"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Address</label>
          <textarea
            value={form.address}
            onChange={(e) => update("address", e.target.value)}
            rows={2}
            className="w-full border border-slate-300 rounded px-3 py-2"
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
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => update("email", e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2"
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
