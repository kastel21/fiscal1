/**
 * Create WebSocket for dashboard - connects to fdms_dashboard group (all devices) or device-specific.
 * When deviceId provided, connects to ws/fdms/device/<device_id>/ for device-specific events.
 * Pass token for JWT auth (required when using JWT, no session).
 */
export function createDashboardWebSocket(onMessage, options = {}) {
  const { deviceId, token } = options;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;

  let url;
  if (deviceId) {
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    url = `${protocol}//${host}/ws/fdms/device/${deviceId}/${qs}`;
  } else {
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    url = `${protocol}//${host}/ws/fdms/dashboard/${qs}`;
  }

  const ws = new WebSocket(url);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onMessage(data);
    } catch (err) {
      console.warn("WebSocket parse error:", err);
    }
  };

  ws.onerror = (e) => console.warn("WebSocket error:", e);
  ws.onclose = () => console.log("WebSocket closed");

  return ws;
}
