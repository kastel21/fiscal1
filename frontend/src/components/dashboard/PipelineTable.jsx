export default function PipelineTable({ data }) {
  if (!data) return null;
  const items = [
    { label: "Draft", value: data.draft, filter: "draft" },
    { label: "Pending", value: data.pending, filter: null },
    { label: "Fiscalised", value: data.fiscalised, filter: "fiscalised" },
    { label: "Failed", value: data.failed, filter: null },
  ];
  return (
    <div className="bg-white shadow rounded-lg p-4">
      <h2 className="font-bold mb-3">Receipt Pipeline</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {items.map(({ label, value, filter }) => (
          <div key={label} className="border rounded p-3">
            <p className="text-sm text-gray-600">{label}</p>
            {filter ? (
              <a href={`/fdms/receipts/?status=${filter}`} className="text-lg font-bold text-indigo-600 hover:underline block">
                {value ?? 0}
              </a>
            ) : (
              <p className="text-lg font-bold">{value ?? 0}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
