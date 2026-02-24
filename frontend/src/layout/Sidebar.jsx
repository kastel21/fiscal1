import React, { useState } from "react";
import { useAuth } from "../auth/AuthContext";

const MAIN_ITEMS = [
  { label: "Dashboard", route: "kpi" },
  { label: "Create Invoice", route: "invoice" },
  { label: "Receipts", route: "/fdms/receipts/" },
  { label: "New Receipt", route: "/fdms/receipts/new/" },
  { label: "Fiscal Day", route: "/fdms/fiscal/" },
];

const SETTINGS_ITEMS = [
  { label: "Company", route: "company" },
  { label: "Devices", route: "devices" },
  { label: "Products", route: "products" },
  { label: "Customers", route: "customers" },
  { label: "Register", route: "/fdms/device/" },
  { label: "Invoice Import", route: "/fdms/invoice-import/" },
  { label: "Credit Note Import", route: "/fdms/credit-note-import/" },
  { label: "QuickBooks", route: "/fdms/quickbooks-invoices/" },
  { label: "Audit", route: "/fdms/audit/" },
  { label: "Logs", route: "/fdms/logs/" },
  { label: "System", route: "system" },
];

const ROLE_MAIN = {
  admin: MAIN_ITEMS,
  operator: [
    { label: "Dashboard", route: "kpi" },
    { label: "Create Invoice", route: "invoice" },
    { label: "Receipts", route: "/fdms/receipts/" },
    { label: "New Receipt", route: "/fdms/receipts/new/" },
    { label: "Fiscal Day", route: "/fdms/fiscal/" },
  ],
  viewer: [{ label: "Dashboard", route: "kpi" }],
};

const ROLE_SETTINGS = {
  admin: SETTINGS_ITEMS,
  operator: [],
  viewer: [],
};

export default function Sidebar({ collapsed, onToggle, onNavigate }) {
  const { role } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(() => localStorage.getItem("fdms-settings-open") === "true");
  const mainItems = ROLE_MAIN[role] || ROLE_MAIN.viewer;
  const settingsItems = ROLE_SETTINGS[role] || [];
  const stored = localStorage.getItem("fdms-sidebar-collapsed");
  const isCollapsed = collapsed ?? (stored === "true");

  const toggle = () => {
    const next = !isCollapsed;
    localStorage.setItem("fdms-sidebar-collapsed", String(next));
    onToggle?.(next);
  };

  const toggleSettings = () => {
    const next = !settingsOpen;
    localStorage.setItem("fdms-settings-open", String(next));
    setSettingsOpen(next);
  };

  return (
    <aside
      className={`${isCollapsed ? "w-20" : "w-64"} bg-slate-800 text-white transition-all duration-300 flex flex-col min-h-screen`}
    >
      <div className="p-4 flex items-center justify-between border-b border-slate-700">
        {!isCollapsed && <span className="font-bold">FDMS</span>}
        <button
          type="button"
          onClick={toggle}
          className="p-2 hover:bg-slate-700 rounded"
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {isCollapsed ? "→" : "←"}
        </button>
      </div>
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {mainItems.map((item) => (
          <SidebarLink key={item.label} item={item} collapsed={isCollapsed} onNavigate={onNavigate} />
        ))}
        {settingsItems.length > 0 && !isCollapsed && (
          <div className="pt-2 mt-2 border-t border-slate-700">
            <button
              type="button"
              onClick={toggleSettings}
              className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg hover:bg-slate-700 text-slate-200 text-left"
            >
              <span className="font-medium">Settings</span>
              <span className={`text-slate-400 transition-transform ${settingsOpen ? "rotate-180" : ""}`}>▼</span>
            </button>
            {settingsOpen && (
              <div className="pl-3 mt-1 space-y-0.5">
                {settingsItems.map((item) => (
                  <SidebarLink key={item.label} item={item} collapsed={false} onNavigate={onNavigate} indent />
                ))}
              </div>
            )}
          </div>
        )}
      </nav>
    </aside>
  );
}

function SidebarLink({ item, collapsed, onNavigate, indent }) {
  const route = item.route;
  const isLink = route?.startsWith("/");

  const content = (
    <>
      {collapsed && !indent ? <span className="text-xs">{item.label[0]}</span> : <span>{item.label}</span>}
    </>
  );

  if (isLink) {
    return (
      <a
        href={route}
        className={`flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-slate-700 text-slate-200 ${indent ? "text-sm" : ""}`}
      >
        {content}
      </a>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onNavigate?.(route)}
      className={`sidebar-link w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-slate-700 text-slate-200 text-left ${indent ? "text-sm" : ""}`}
    >
      {content}
    </button>
  );
}
