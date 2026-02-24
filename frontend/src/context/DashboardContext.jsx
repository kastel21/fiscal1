import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { fetchMetrics } from "../services/api";
import { createDashboardWebSocket } from "../services/websocket";

const DashboardContext = createContext(null);

export function DashboardProvider({ children, selectedDeviceId, token }) {
  const [metrics, setMetrics] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [receiptProgress, setReceiptProgress] = useState(null);

  const deviceIdForApi = selectedDeviceId && typeof selectedDeviceId === "object"
    ? selectedDeviceId.device_id
    : selectedDeviceId;

  const loadMetrics = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchMetrics(deviceIdForApi);
      setMetrics(data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  }, [deviceIdForApi]);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  useEffect(() => {
    const deviceId = selectedDeviceId && typeof selectedDeviceId === "object"
      ? selectedDeviceId.device_id
      : selectedDeviceId;
    const ws = createDashboardWebSocket(
      (data) => {
        if (data.type === "metrics.updated" && data.metrics) {
          setMetrics(data.metrics);
        }
        if (data.type === "receipt.progress") {
          setReceiptProgress(data);
        }
        if (data.type === "receipt.completed" || data.type === "receipt.failed") {
          setReceiptProgress(null);
          setActivity((prev) => [{ ...data, ts: new Date().toISOString() }, ...prev].slice(0, 50));
        }
        if (data.type === "fiscal.opened" || data.type === "fiscal.closed") {
          setActivity((prev) => [{ ...data, ts: new Date().toISOString() }, ...prev].slice(0, 50));
        }
        if (data.type === "activity" || data.type === "certificate.updated") {
          setActivity((prev) => [{ ...data, ts: new Date().toISOString() }, ...prev].slice(0, 50));
        }
      },
      { deviceId, token }
    );
    return () => ws.close();
  }, [selectedDeviceId, token]);

  return (
    <DashboardContext.Provider
      value={{
        metrics,
        activity,
        receiptProgress,
        loading,
        error,
        refresh: loadMetrics,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used within DashboardProvider");
  return ctx;
}
