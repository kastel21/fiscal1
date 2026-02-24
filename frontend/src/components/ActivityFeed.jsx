export default function ActivityFeed({ events = [], maxHeight = 300 }) {
  const getStatusColor = (type) => {
    if (type?.includes?.("completed") || type?.includes?.("opened")) return "bg-green-100 text-green-800";
    if (type?.includes?.("failed") || type?.includes?.("error")) return "bg-red-100 text-red-800";
    return "bg-slate-100 text-slate-800";
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-4">
      <h3 className="font-semibold text-slate-800 mb-3">Activity Feed</h3>
      <div className="space-y-2 overflow-y-auto" style={{ maxHeight }}>
        {events.length === 0 ? (
          <p className="text-slate-500 text-sm">No recent activity</p>
        ) : (
          events.map((e, i) => (
            <div key={i} className="flex gap-2 text-sm border-b border-slate-100 pb-2 last:border-0">
              <span className="text-slate-400 shrink-0">
                {e.ts ? new Date(e.ts).toLocaleTimeString() : "—"}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs shrink-0 ${getStatusColor(e.type)}`}>
                {e.type || "event"}
              </span>
              <span className="text-slate-700 truncate">
                {e.message || e.invoice_no || e.receipt_global_no || JSON.stringify(e)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
