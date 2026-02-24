import React, { useEffect, useState } from "react";
import axios from "axios";
import FiscalCard from "./FiscalCard";
import ReceiptTable from "./ReceiptTable";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [dashboardRes, receiptsRes] = await Promise.all([
          axios.get("/api/fdms/dashboard/", { withCredentials: true }),
          axios.get("/api/fdms/receipts/", { withCredentials: true }),
        ]);
        setData(dashboardRes.data);
        setReceipts(receiptsRes.data.receipts || []);
        setError(null);
      } catch (err) {
        setError(err.response?.data?.detail || err.message || "Failed to load");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return <div className="text-gray-500 p-6">Loading...</div>;
  if (error) return <div className="text-red-600 p-6">Error: {error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-4 shadow rounded">
          <h2 className="font-bold mb-2">Device</h2>
          <p>ID: {data.device?.deviceID ?? "—"}</p>
          <p>Status: {data.device?.status ?? "—"}</p>
        </div>
        <FiscalCard fiscal={data.fiscal} />
        <div className="bg-white p-4 shadow rounded">
          <h2 className="font-bold mb-2">Last Receipt</h2>
          <p>Global No: {data.lastReceipt?.globalNo ?? "—"}</p>
          <p>Total: {data.lastReceipt?.total ?? "—"}</p>
          <p>Server Verified: {data.lastReceipt?.serverVerified ? "YES" : "NO"}</p>
        </div>
      </div>
      <ReceiptTable receipts={receipts} />
    </div>
  );
}
