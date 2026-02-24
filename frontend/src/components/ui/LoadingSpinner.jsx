import React from "react";

export default function LoadingSpinner({ size = "md", className = "" }) {
  const sizes = { sm: "w-5 h-5", md: "w-8 h-8", lg: "w-12 h-12" };
  return (
    <div className={`animate-spin rounded-full border-2 border-slate-200 border-t-indigo-600 ${sizes[size] || sizes.md} ${className}`} />
  );
}
