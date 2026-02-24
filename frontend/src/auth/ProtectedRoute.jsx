import React from "react";
import { useAuth } from "./AuthContext";
import LoginPage from "../pages/LoginPage";

export default function ProtectedRoute({ children }) {
  const { token, ready } = useAuth();

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="animate-spin w-10 h-10 border-2 border-indigo-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!token) {
    return <LoginPage />;
  }

  return children;
}
