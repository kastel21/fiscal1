export default function ChartPanel({ title, children }) {
  return (
    <div className="bg-white rounded-lg shadow-md p-4">
      {title && <h3 className="font-semibold text-slate-800 mb-3">{title}</h3>}
      {children}
    </div>
  );
}
