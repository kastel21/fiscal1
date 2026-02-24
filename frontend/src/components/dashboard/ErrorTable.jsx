export default function ErrorTable({ errors }) {
  if (!errors || errors.length === 0) {
    return (
      <div className="bg-white shadow rounded-lg p-4">
        <h2 className="font-bold mb-3">Errors and Risks</h2>
        <p className="text-green-600">No errors in period.</p>
      </div>
    );
  }
  return (
    <div className="bg-white shadow rounded-lg p-4">
      <h2 className="font-bold mb-3">Errors and Risks</h2>
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left py-2">Endpoint</th>
            <th className="text-left py-2">Status</th>
            <th className="text-left py-2">Error</th>
            <th className="text-left py-2">Operation ID</th>
          </tr>
        </thead>
        <tbody>
          {errors.map((e) => (
            <tr key={e.id} className="border-b">
              <td className="py-2">{e.endpoint}</td>
              <td className="py-2">{e.statusCode ?? "—"}</td>
              <td className="py-2">{e.error}</td>
              <td className="py-2">
                {e.operationId ? (
                  <a href={`/fdms/logs/?operation_id=${encodeURIComponent(e.operationId)}`} className="text-indigo-600 hover:underline font-mono text-xs">
                    {e.operationId}
                  </a>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
