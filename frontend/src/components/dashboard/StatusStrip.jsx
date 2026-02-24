export default function StatusStrip({ data }) {
  if (!data) return null;
  const items = [
    { label: "Fiscal Day", value: data.fiscalDay },
    { label: "FDMS", value: data.fdmsConnectivity },
    { label: "Certificate", value: data.certificate },
    { label: "Last Sync", value: data.lastSync ? new Date(data.lastSync).toLocaleString() : "—" },
  ];
  return (
    <div className="bg-white shadow rounded-lg p-4">
      <h2 className="font-bold mb-3">Status</h2>
      <div className="flex flex-wrap gap-6">
        {items.map(({ label, value }) => (
          <div key={label}><span className="text-gray-600">{label}:</span> <span className="font-medium">{value}</span></div>
        ))}
      </div>
    </div>
  );
}
