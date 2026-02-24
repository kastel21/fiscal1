import React, { useState } from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import { DeviceProvider, useDevice } from "../context/DeviceContext";

function LayoutInner({ children, onViewChange }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("fdms-sidebar-collapsed") === "true");
  const { devices, selectedDevice, setSelectedDevice } = useDevice();

  return (
    <div className="flex min-h-screen bg-slate-100">
      <Sidebar collapsed={sidebarCollapsed} onToggle={setSidebarCollapsed} onNavigate={onViewChange} />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar
          onViewChange={onViewChange}
          currentView={currentView}
          devices={devices}
          selectedDevice={selectedDevice}
          onDeviceChange={setSelectedDevice}
        />
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function Layout({ children, onViewChange }) {
  return (
    <DeviceProvider>
      <LayoutInner onViewChange={onViewChange}>{children}</LayoutInner>
    </DeviceProvider>
  );
}
