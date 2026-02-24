import React, { useEffect, useState } from "react";
import axios from "axios";
import TimeRangeFilter from "./TimeRangeFilter";
import StatusStrip from "./StatusStrip";
import MetricsGrid from "./MetricsGrid";
import PipelineTable from "./PipelineTable";
import ErrorTable from "./ErrorTable";
import ComplianceSnapshot from "./ComplianceSnapshot";
import AlertBar from "./AlertBar";
import QuickBooksPanel from "./QuickBooksPanel";

export default function DashboardPage() {
  const [range, setRange] = useState("today");
  const [data, setData] = useState(null);
  const [errors, setErrors] = useState([]);
  const [qb, setQb] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        setLoading(true);
        const [summaryRes, errorsRes, qbRes] = await Promise.all([
          axios.get(`/api/dashboard/summary/?range=${range}`, { withCredentials: true }),
          axios.get(`/api/dashboard/errors/?range=${range}`, { withCredentials: true }),
          axios.get("/api/dashboard/quickbooks/", { withCredentials: true }),
        ]);
        setData(summaryRes.data);
        setErrors(errorsRes.data.errors || []);
        setQb(qbRes.data);
        setErr(null);
      } catch (e) {
        setErr(e.response?.data?.detail || e.message || "Failed to load");
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [range]);

  if (loading) return <div className="text-gray-500 p-6">Loading...</div>;
  if (err) return <div className="text-red-600 p-6">Error: {err}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">System Dashboard</h1>
        <div className="flex items-center gap-4">
          <TimeRangeFilter value={range} onChange={setRange} />
          <a
            href={`/api/dashboard/export/pdf/?range=${range}`}
            className="text-sm text-indigo-600 hover:underline"
          >
            Export PDF
          </a>
          <a
            href={`/api/dashboard/export/excel/?range=${range}`}
            className="text-sm text-indigo-600 hover:underline"
          >
            Export Excel
          </a>
        </div>
      </div>

      {data.alerts && data.alerts.length > 0 && (
        <AlertBar alerts={data.alerts} />
      )}

      <StatusStrip data={data.status} />
      <MetricsGrid data={data.metrics} />
      <PipelineTable data={data.pipeline} />
      <QuickBooksPanel data={qb} />
      <ErrorTable errors={errors} />
      <ComplianceSnapshot data={data.compliance} />
    </div>
  );
}
