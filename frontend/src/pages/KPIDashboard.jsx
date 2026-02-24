import React from "react";
import { DashboardProvider, useDashboard } from "../context/DashboardContext";
import { useDevice } from "../context/DeviceContext";
import { useAuth } from "../auth/AuthContext";
import KPICard from "../components/KPICard";
import ProgressBar from "../components/ProgressBar";
import ActivityFeed from "../components/ActivityFeed";
import ChartPanel from "../components/ChartPanel";
import ReceiptsTrendChart from "../components/charts/ReceiptsTrendChart";
import TaxBreakdownChart from "../components/charts/TaxBreakdownChart";
import SalesVolumeChart from "../components/charts/SalesVolumeChart";
import CertificateExpiry from "../widgets/CertificateExpiry";

function KPIDashboardContent() {
  const { metrics, activity, receiptProgress, loading, error, refresh } = useDashboard();
  const { selectedDevice } = useDevice();

  if (loading) return <div className="text-slate-500 p-6">Loading metrics...</div>;
  if (error) return <div className="text-red-600 p-6">Error: {error}</div>;
  if (!metrics) return null;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-slate-800">Real-Time KPI Dashboard</h1>
        <button
          onClick={refresh}
          className="text-sm text-indigo-600 hover:underline"
        >
          Refresh
        </button>
      </div>

      {receiptProgress && (
        <ProgressBar
          percent={receiptProgress.percent ?? 0}
          stage={receiptProgress.stage}
          label="Receipt submission"
        />
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KPICard
          title="Active Devices"
          value={`${metrics.activeDevices}/${metrics.totalDevices}`}
          statusColor="blue"
        />
        <KPICard
          title="Receipts Today"
          value={metrics.receiptsToday ?? 0}
          statusColor="green"
        />
        <KPICard
          title="Failed Receipts"
          value={metrics.failedReceipts ?? 0}
          statusColor={metrics.failedReceipts > 0 ? "red" : "gray"}
        />
        <KPICard
          title="Success Rate (24h)"
          value={`${metrics.successRate ?? 100}%`}
          statusColor={metrics.successRate >= 99 ? "green" : "amber"}
        />
        <KPICard
          title="FDMS Latency"
          value={metrics.avgLatencyMs != null ? `${metrics.avgLatencyMs}ms` : "—"}
          statusColor="gray"
        />
        <KPICard
          title="Queue Depth"
          value={metrics.queueDepth ?? 0}
          statusColor={metrics.queueDepth > 0 ? "amber" : "gray"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartPanel>
          <ReceiptsTrendChart receiptsPerHour={metrics.receiptsPerHour || []} />
        </ChartPanel>
        <ChartPanel>
          <TaxBreakdownChart taxBreakdown={metrics.taxBreakdown || []} />
        </ChartPanel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartPanel title="Sales by Currency">
          <SalesVolumeChart sales={metrics.sales || {}} />
        </ChartPanel>
        <div className="space-y-6">
          <ActivityFeed events={activity} maxHeight={240} />
          <CertificateExpiry deviceId={selectedDevice} />
        </div>
      </div>
    </div>
  );
}

export default function KPIDashboard() {
  const { selectedDevice } = useDevice();
  const { token } = useAuth();
  return (
    <DashboardProvider selectedDeviceId={selectedDevice} token={token}>
      <KPIDashboardContent />
    </DashboardProvider>
  );
}
