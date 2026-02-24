export default function ProgressBar({ percent = 0, stage = "", label = "" }) {
  return (
    <div className="bg-slate-100 rounded-lg p-4">
      {label && <p className="text-sm font-medium text-slate-700 mb-2">{label}</p>}
      <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-600 transition-all duration-300 ease-out"
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
      {stage && <p className="text-xs text-slate-600 mt-2">{stage}</p>}
    </div>
  );
}
