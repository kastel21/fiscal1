import React, { useEffect, useState } from "react";
import axios from "axios";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";

export default function CertificateExpiry({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!!deviceId);

  useEffect(() => {
    if (!deviceId) {
      setData(null);
      setLoading(false);
      return;
    }
    const pk = typeof deviceId === "object" ? deviceId?.id : deviceId;
    if (!pk) return;
    setLoading(true);
    axios
      .get(`/api/devices/${pk}/certificate-status/`, { withCredentials: true })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [deviceId]);

  if (!deviceId) {
    return (
      <Card title="Certificate">
        <p className="text-slate-500 text-sm">Select a device to view certificate status.</p>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card title="Certificate">
        <div className="animate-pulse h-12 bg-slate-200 rounded" />
      </Card>
    );
  }

  const days = data?.daysRemaining ?? null;
  const expiresOn = data?.expiresOn ?? null;

  let variant = "default";
  if (days !== null) {
    if (days > 60) variant = "success";
    else if (days > 30) variant = "warning";
    else variant = "danger";
  }

  return (
    <Card title="Certificate">
      <div className="space-y-2">
        {expiresOn && <p className="text-sm text-slate-600">Expires: {expiresOn}</p>}
        {days !== null ? (
          <Badge variant={variant}>
            {days} days remaining
          </Badge>
        ) : (
          <p className="text-slate-500 text-sm">No certificate data</p>
        )}
      </div>
    </Card>
  );
}
