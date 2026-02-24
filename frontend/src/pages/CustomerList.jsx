import React, { useEffect, useState } from "react";
import axios from "axios";

function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  if (el) return el.getAttribute("content") || "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

export default function CustomerList({ onAdd, onEdit }) {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get("/api/customers/", { withCredentials: true })
      .then((r) => setCustomers(r.data.customers || []))
      .catch(() => setCustomers([]))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id) => {
    if (!window.confirm("Deactivate this customer?")) return;
    try {
      await axios.delete(`/api/customers/${id}/`, {
        withCredentials: true,
        headers: { "X-CSRFToken": getCsrfToken() },
      });
      setCustomers((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      alert(err.response?.data?.error || "Failed to deactivate");
    }
  };

  if (loading) return <p className="text-slate-600">Loading customers...</p>;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-slate-800">Customers</h1>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            Add Customer
          </button>
        )}
      </div>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 border-b">
              <th className="text-left py-3 px-4">Name</th>
              <th className="text-left py-3 px-4">TIN</th>
              <th className="text-left py-3 px-4">Phone</th>
              <th className="text-left py-3 px-4">Email</th>
              <th className="text-left py-3 px-4">Status</th>
              <th className="text-left py-3 px-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {customers.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-6 text-center text-slate-500">
                  No customers. Add a customer to get started.
                </td>
              </tr>
            ) : (
              customers.map((c) => (
                <tr key={c.id} className="border-b hover:bg-slate-50">
                  <td className="py-3 px-4 font-medium">{c.name}</td>
                  <td className="py-3 px-4">{c.tin || "—"}</td>
                  <td className="py-3 px-4">{c.phone || "—"}</td>
                  <td className="py-3 px-4">{c.email || "—"}</td>
                  <td className="py-3 px-4">{c.is_active ? "Active" : "Inactive"}</td>
                  <td className="py-3 px-4">
                    {onEdit && (
                      <button type="button" onClick={() => onEdit(c.id)} className="text-indigo-600 hover:underline mr-2">
                        Edit
                      </button>
                    )}
                    {c.is_active && (
                      <button type="button" onClick={() => handleDelete(c.id)} className="text-red-600 hover:underline">
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
