export default function KPICard({ title, value, subtitle, statusColor = "gray", className = "" }) {
  const colors = {
    green: "border-l-green-500",
    amber: "border-l-amber-500",
    red: "border-l-red-500",
    blue: "border-l-blue-500",
    gray: "border-l-slate-400",
  };
  return (
    <div
      className={`bg-white p-5 rounded-lg shadow-md border-l-4 ${colors[statusColor] || colors.gray} ${className}`}
    >
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{title}</p>
      <p className="text-2xl font-bold text-slate-800 mt-1">{value}</p>
      {subtitle && <p className="text-sm text-slate-600 mt-1">{subtitle}</p>}
    </div>
  );
}
