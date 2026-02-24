import React, { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import DeviceSelector from "../devices/DeviceSelector";

export default function Topbar({ devices, selectedDevice, onDeviceChange }) {
  const { user, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  return (
    <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4">
      <div className="flex items-center gap-4">
        <DeviceSelector
          devices={devices}
          selected={selectedDevice}
          onChange={onDeviceChange}
          compact
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="p-2 text-slate-500 hover:text-slate-700 rounded-lg hover:bg-slate-100"
          aria-label="Notifications"
        >
          <span className="text-lg">&#128276;</span>
        </button>
        <div className="relative">
          <button
            type="button"
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-slate-100"
          >
            <span className="text-sm font-medium text-slate-700">{user?.username || "User"}</span>
            <span className="text-slate-400">&#9660;</span>
          </button>
          {userMenuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setUserMenuOpen(false)} aria-hidden="true" />
              <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border border-slate-200 py-1 z-20">
                <button
                  type="button"
                  onClick={() => { logout(); setUserMenuOpen(false); }}
                  className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                >
                  Logout
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
