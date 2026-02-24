export default function TimeRangeFilter({ value, onChange }) {
  return (
    <div className="flex gap-2">
      {["today", "week", "month"].map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => onChange(r)}
          className={`px-3 py-1 rounded text-sm font-medium ${
            value === r
              ? "bg-indigo-600 text-white"
              : "bg-gray-200 text-gray-700 hover:bg-gray-300"
          }`}
        >
          {r === "today" ? "Today" : r === "week" ? "This Week" : "This Month"}
        </button>
      ))}
    </div>
  );
}
