export default function ComplianceSnapshot({ data }) {
  if (!data) return null;
  return (
    <div className="bg-white shadow rounded-lg p-4 print:shadow-none print:border">
      <h2 className="font-bold mb-3">Compliance Snapshot</h2>
      <div className="space-y-2">
        <div><span className="text-gray-600">Last OpenDay:</span> {data.lastOpenDay ? new Date(data.lastOpenDay).toLocaleString() : "—"}</div>
        <div><span className="text-gray-600">Last CloseDay:</span> {data.lastCloseDay ? new Date(data.lastCloseDay).toLocaleString() : "—"}</div>
        <div><span className="text-gray-600">Last Ping:</span> {data.lastPing ? new Date(data.lastPing).toLocaleString() : "—"}</div>
        {data.reportingFrequency != null && (
          <div><span className="text-gray-600">Reporting frequency:</span> {data.reportingFrequency} min</div>
        )}
        <div><span className="text-gray-600">Last receiptGlobalNo:</span> {data.lastReceiptGlobalNo ?? "—"}</div>
        {data.outstandingRisks && data.outstandingRisks.length > 0 && (
          <div><span className="text-gray-600">Open risks:</span> {data.outstandingRisks.join(", ")}</div>
        )}
      </div>
    </div>
  );
}
