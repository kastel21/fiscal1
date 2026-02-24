export default function InvoiceHeader({ deviceId, setDeviceId, currency, setCurrency, devices = [] }) {
  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4">
      <h2 className="font-semibold text-slate-800 mb-3">Invoice Header</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Device</label>
          <select
            value={deviceId ?? ""}
            onChange={(e) => setDeviceId(e.target.value ? parseInt(e.target.value, 10) : null)}
            className="w-full border border-slate-300 rounded px-3 py-2"
          >
            <option value="">Select device</option>
            {devices.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                Device #{d.device_id} ({d.fiscal_day_status || "—"})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Currency</label>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="w-full border border-slate-300 rounded px-3 py-2"
          >
            <option value="ZWL">ZWL</option>
            <option value="USD">USD</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-600 mb-1">Date</label>
          <input
            type="text"
            value={new Date().toISOString().slice(0, 10)}
            readOnly
            className="w-full border border-slate-200 rounded px-3 py-2 bg-slate-50"
          />
        </div>
      </div>
    </div>
  );
}
