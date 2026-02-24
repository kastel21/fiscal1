import React from "react";

export default function FiscalCard({ fiscal }) {
  return (
    <div className="bg-white p-4 shadow rounded">
      <h2 className="font-bold mb-2">Fiscal Day</h2>
      <p>Day No: {fiscal?.dayNo ?? "—"}</p>
      <p>Status: {fiscal?.status ?? "—"}</p>
      <p>Receipts: {fiscal?.receiptCount ?? 0}</p>
    </div>
  );
}
