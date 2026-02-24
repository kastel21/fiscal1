import React from "react";
import { theme } from "../../theme";

export default function Card({ title, children, className = "" }) {
  return (
    <div className={`bg-white ${theme.radius} ${theme.shadow} overflow-hidden ${className}`}>
      {title && (
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
}
