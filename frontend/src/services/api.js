import axios from "axios";

export async function fetchMetrics(deviceId = null) {
  const params = deviceId ? { device_id: deviceId } : {};
  const { data } = await axios.get("/api/dashboard/metrics/", { params, withCredentials: true });
  return data;
}
