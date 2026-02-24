import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import axios from "axios";

function decodeJwtPayload(token) {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64);
    return JSON.parse(json);
  } catch {
    return null;
  }
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [role, setRole] = useState("viewer");
  const [ready, setReady] = useState(false);

  const applyToken = useCallback((t) => {
    if (!t) {
      setToken(null);
      setUser(null);
      setRole("viewer");
      delete axios.defaults.headers.common["Authorization"];
      return;
    }
    setToken(t);
    axios.defaults.headers.common["Authorization"] = `Bearer ${t}`;
    try {
      const payload = decodeJwtPayload(t);
      if (payload) {
        setUser({ username: payload.username || payload.sub });
        setRole(payload.role || "viewer");
      } else {
        setUser(null);
        setRole("viewer");
      }
    } catch {
      setUser(null);
      setRole("viewer");
    }
  }, []);

  const login = useCallback(async (username, password) => {
    const { data } = await axios.post("/api/token/", { username, password });
    applyToken(data.access);
  }, [applyToken]);

  const logout = useCallback(() => {
    applyToken(null);
  }, [applyToken]);

  const refreshToken = useCallback(async () => {
    const refresh = localStorage.getItem("fdms_refresh_token");
    if (!refresh) return;
    try {
      const { data } = await axios.post("/api/token/refresh/", { refresh });
      applyToken(data.access);
    } catch {
      applyToken(null);
    }
  }, [applyToken]);

  useEffect(() => {
    setReady(true);
  }, []);

  return (
    <AuthContext.Provider value={{ user, role, token, login, logout, ready, refreshToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
