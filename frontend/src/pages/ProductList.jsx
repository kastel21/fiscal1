import React, { useEffect, useState } from "react";
import axios from "axios";

function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  if (el) return el.getAttribute("content") || "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

export default function ProductList({ onAdd, onEdit }) {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get("/api/products/", { withCredentials: true })
      .then((r) => setProducts(r.data.products || []))
      .catch(() => setProducts([]))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id) => {
    if (!window.confirm("Deactivate this product?")) return;
    try {
      await axios.delete(`/api/products/${id}/`, {
        withCredentials: true,
        headers: { "X-CSRFToken": getCsrfToken() },
      });
      setProducts((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      alert(err.response?.data?.error || "Failed to deactivate");
    }
  };

  if (loading) return <p className="text-slate-600">Loading products...</p>;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-slate-800">Products</h1>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            Add Product
          </button>
        )}
      </div>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 border-b">
              <th className="text-left py-3 px-4">Name</th>
              <th className="text-right py-3 px-4">Price</th>
              <th className="text-right py-3 px-4">Tax %</th>
              <th className="text-left py-3 px-4">HS Code</th>
              <th className="text-left py-3 px-4">Status</th>
              <th className="text-left py-3 px-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {products.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-6 text-center text-slate-500">
                  No products. Add a product to get started.
                </td>
              </tr>
            ) : (
              products.map((p) => (
                <tr key={p.id} className="border-b hover:bg-slate-50">
                  <td className="py-3 px-4 font-medium">{p.name}</td>
                  <td className="py-3 px-4 text-right">{p.price}</td>
                  <td className="py-3 px-4 text-right">{p.tax_percent}</td>
                  <td className="py-3 px-4">{p.hs_code || "—"}</td>
                  <td className="py-3 px-4">{p.is_active ? "Active" : "Inactive"}</td>
                  <td className="py-3 px-4">
                    {onEdit && (
                      <button type="button" onClick={() => onEdit(p.id)} className="text-indigo-600 hover:underline mr-2">
                        Edit
                      </button>
                    )}
                    {p.is_active && (
                      <button type="button" onClick={() => handleDelete(p.id)} className="text-red-600 hover:underline">
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
