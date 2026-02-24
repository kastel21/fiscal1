import React, { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";

const DeviceContext = createContext(null);

export function DeviceProvider({ children }) {
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);

  useEffect(() => {
    axios.get("/api/devices/", { withCredentials: true })
      .then((r) => setDevices(r.data.devices || []))
      .catch(() => setDevices([]));
  }, []);

  return (
    <DeviceContext.Provider value={{ devices, selectedDevice, setSelectedDevice }}>
      {children}
    </DeviceContext.Provider>
  );
}

export function useDevice() {
  const ctx = useContext(DeviceContext);
  return ctx || { devices: [], selectedDevice: null, setSelectedDevice: () => {} };
}
