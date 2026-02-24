import React, { useEffect, useState } from "react";
import axios from "axios";

function certStatusColor(validTill) {
  if (!validTill) return "text-slate-500";
  const d = new Date(validTill);
  const now = new Date();
  const days = Math.ceil((d - now) / (1000 * 60 * 60 * 24));
  if (days > 60) return "text-green-600";
  if (days > 30) return "text-amber-600";
  return "text-red-600";
}

function certStatusLabel(validTill) {
  if (!validTill) return "—";
  const d = new Date(validTill);
  const now = new Date();
  const days = Math.ceil((d - now) / (1000 * 60 * 60 * 24));
  if (days > 60) return `${days} days`;
  if (days > 30) return `${days} days (expiring soon)`;
  if (days > 0) return `${days} days (expiring soon)`;
  return "Expired";
}

export default function DeviceList({ onSelectDevice }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get("/api/devices/", { withCredentials: true })
      .then((r) => setDevices(r.data.devices || []))
      .catch(() => setDevices([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div>
        <p className="text-slate-600">Loading devices...</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Fiscal Devices</h1>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 border-b">
              <th className="text-left py-3 px-4">Device ID</th>
              <th className="text-left py-3 px-4">Serial</th>
              <th className="text-left py-3 px-4">Status</th>
              <th className="text-left py-3 px-4">Certificate</th>
              <th className="text-left py-3 px-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {devices.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-slate-500">
                  No registered devices. Use the <a href="/fdms/device/" className="text-indigo-600 hover:underline">Device</a> page to register.
                </td>
              </tr>
            ) : (
              devices.map((d) => (
                <tr key={d.id} className="border-b hover:bg-slate-50">
                  <td className="py-3 px-4 font-medium">#{d.device_id}</td>
                  <td className="py-3 px-4">{d.device_serial_no || "—"}</td>
                  <td className="py-3 px-4">{d.fiscal_day_status || "—"}</td>
                  <td className={`py-3 px-4 ${certStatusColor(d.certificate_valid_till)}`}>
                    {certStatusLabel(d.certificate_valid_till)}
                  </td>
                  <td className="py-3 px-4">
                    <button
                      type="button"
                      onClick={() => onSelectDevice && onSelectDevice(d.id)}
                      className="text-indigo-600 hover:underline"
                    >
                      View
                    </button>
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
