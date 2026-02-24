export default function AlertBar({ alerts }) {
  if (!alerts || alerts.length === 0) return null;
  return (
    <div className="space-y-2">
      {alerts.map((a, i) => (
        <div key={i} className={`p-3 rounded ${a.severity === "CRITICAL" ? "bg-red-100 text-red-800" : "bg-amber-50 text-amber-800"}`}>
          <span className="font-medium">{a.severity}: {a.message}</span>
        </div>
      ))}
    </div>
  );
}
