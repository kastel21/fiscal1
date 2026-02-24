import React from "react";

export function Table({ children, className = "" }) {
  return <table className={`w-full text-sm ${className}`}>{children}</table>;
}

export function TableHead({ children }) {
  return <thead><tr className="border-b bg-slate-100">{children}</tr></thead>;
}

export function TableBody({ children }) {
  return <tbody>{children}</tbody>;
}

export function TableRow({ children, className = "" }) {
  return <tr className={`border-b hover:bg-slate-50 ${className}`}>{children}</tr>;
}

export function TableCell({ children, className = "", header }) {
  const Tag = header ? "th" : "td";
  return <Tag className={`py-3 px-4 text-left ${className}`}>{children}</Tag>;
}
