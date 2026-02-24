import React, { useEffect, useState } from "react";
import axios from "axios";

function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  if (el) return el.getAttribute("content") || "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

function certStatusClass(validTill) {
  if (!validTill) return "bg-slate-100 text-slate-700";
  const d = new Date(validTill);
  const now = new Date();
  const days = Math.ceil((d - now) / (1000 * 60 * 60 * 24));
  if (days > 60) return "bg-green-100 text-green-800";
  if (days > 30) return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}

export default function DeviceDetail({ devicePk, onBack }) {
  const [device, setDevice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState(null);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!devicePk) return;
    setLoading(true);
    axios
      .get(`/api/devices/${devicePk}/`, { withCredentials: true })
      .then((r) => setDevice(r.data.device))
      .catch(() => setDevice(null))
      .finally(() => setLoading(false));
  }, [devicePk]);

  const doOpenDay = async () => {
    setMessage(null);
    setAction("opening");
    try {
      await axios.post(`/api/devices/${devicePk}/open-day/`, {}, {
        withCredentials: true,
        headers: { "X-CSRFToken": getCsrfToken(), "Content-Type": "application/json" },
      });
      setMessage({ success: true, text: "Fiscal day opened successfully" });
      const r = await axios.get(`/api/devices/${devicePk}/`, { withCredentials: true });
      setDevice(r.data.device);
    } catch (err) {
      setMessage({ error: err.response?.data?.error || err.message });
    } finally {
      setAction(null);
    }
  };

  const doCloseDay = async () => {
    setMessage(null);
    setAction("closing");
    try {
      await axios.post(`/api/devices/${devicePk}/close-day/`, {}, {
        withCredentials: true,
        headers: { "X-CSRFToken": getCsrfToken(), "Content-Type": "application/json" },
      });
      setMessage({ success: true, text: "Fiscal day close initiated" });
      const r = await axios.get(`/api/devices/${devicePk}/`, { withCredentials: true });
      setDevice(r.data.device);
    } catch (err) {
      setMessage({ error: err.response?.data?.error || err.message });
    } finally {
      setAction(null);
    }
  };

  if (!devicePk) return null;
  if (loading) return <p className="text-slate-600">Loading...</p>;
  if (!device) return <p className="text-red-600">Device not found</p>;

  const certTill = device.certificate_valid_till;
  const isOpen = device.fiscal_day_status === "FiscalDayOpened" || device.fiscal_day_status === "FiscalDayCloseFailed";

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        {onBack && (
          <button type="button" onClick={onBack} className="text-indigo-600 hover:underline">
            ← Back
          </button>
        )}
        <h1 className="text-2xl font-bold text-slate-800">Device #{device.device_id}</h1>
      </div>
      <div className="bg-white rounded-lg shadow p-6 space-y-4 max-w-lg">
        <div className="flex justify-between">
          <span className="text-slate-600">Fiscal Day Status</span>
          <span className="font-medium">{device.fiscal_day_status || "—"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-600">Last Fiscal Day No</span>
          <span>{device.last_fiscal_day_no ?? "—"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-600">Last Receipt Global No</span>
          <span>{device.last_receipt_global_no ?? "—"}</span>
        </div>
        <div>
          <span className="text-slate-600 block mb-1">Certificate Expiry</span>
          <span className={`inline-block px-3 py-1 rounded text-sm font-medium ${certStatusClass(certTill)}`}>
            {certTill || "—"}
          </span>
        </div>
        {message && (
          <div className={`p-4 rounded-lg ${message.error ? "bg-red-50 text-red-800" : "bg-green-50 text-green-800"}`}>
            {message.error || message.text}
          </div>
        )}
        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={doOpenDay}
            disabled={!!action || isOpen}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {action === "opening" ? "Opening..." : "Open Day"}
          </button>
          <button
            type="button"
            onClick={doCloseDay}
            disabled={!!action || !isOpen}
            className="px-4 py-2 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {action === "closing" ? "Closing..." : "Close Day"}
          </button>
        </div>
      </div>
    </div>
  );
}
