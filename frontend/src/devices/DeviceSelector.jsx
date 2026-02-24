import React from "react";

export default function DeviceSelector({ devices = [], selected, onChange, compact }) {
  if (devices.length === 0) return null;

  const sel = selected && devices.find((d) => d.id === selected.id || d.id === selected);
  const value = sel ? (sel.id ?? sel) : "";

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-slate-600">Device:</label>
      <select
        value={value}
        onChange={(e) => {
          const id = e.target.value ? parseInt(e.target.value, 10) : null;
          const d = devices.find((dev) => dev.id === id);
          onChange?.(d || id);
        }}
        className="border border-slate-300 rounded-lg px-3 py-2 text-sm min-w-[160px]"
      >
        <option value="">All devices</option>
        {devices.map((d) => (
          <option key={d.id} value={d.id}>
            #{d.device_id} {d.device_serial_no ? `(${d.device_serial_no})` : ""} – {d.fiscal_day_status || "—"}
          </option>
        ))}
      </select>
    </div>
  );
}
