export default function QuickBooksPanel({ data }) {
  if (!data) return null;
  return (
    <div className="bg-white shadow rounded-lg p-4">
      <h2 className="font-bold mb-3">QuickBooks Integration</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div><span className="text-gray-600 text-sm">Invoices received:</span> <span className="font-bold">{data.invoicesReceived ?? 0}</span></div>
        <div><span className="text-gray-600 text-sm">Fiscalised:</span> <span className="font-bold">{data.fiscalised ?? 0}</span></div>
        <div><span className="text-gray-600 text-sm">Pending:</span> <span className="font-bold">{data.pending ?? 0}</span></div>
        <div><span className="text-gray-600 text-sm">Failed:</span> <span className="font-bold">{data.failed ?? 0}</span></div>
      </div>
      {data.lastWebhookTime && (
        <p className="mt-2 text-sm text-gray-500">Last webhook: {new Date(data.lastWebhookTime).toLocaleString()}</p>
      )}
    </div>
  );
}
