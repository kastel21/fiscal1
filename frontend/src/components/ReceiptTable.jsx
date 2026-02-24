import React from "react";

export default function ReceiptTable({ receipts }) {
  if (!receipts?.length) return <div className="bg-white p-6 shadow rounded text-gray-500">No receipts.</div>;

  return (
    <div className="bg-white shadow rounded overflow-hidden">
      <h2 className="font-bold p-4 border-b">Recent Receipts</h2>
      <table className="min-w-full">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Device</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Fiscal Day</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Receipt No</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Total</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {receipts.map((r) => (
            <tr key={r.id} className="hover:bg-gray-50">
              <td className="px-6 py-4">{r.deviceId}</td>
              <td className="px-6 py-4">{r.fiscalDayNo}</td>
              <td className="px-6 py-4 font-mono">{r.receiptGlobalNo}</td>
              <td className="px-6 py-4">{r.total ?? "—"}</td>
              <td className="px-6 py-4 text-sm text-gray-500">{r.createdAt ? new Date(r.createdAt).toLocaleString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
