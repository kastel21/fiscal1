import React, { useEffect, useState } from "react";
import axios from "axios";

export default function TestEnvBanner() {
  const [fdmsEnv, setFdmsEnv] = useState(null);

  useEffect(() => {
    axios
      .get("/api/config/env/", { withCredentials: true })
      .then((r) => setFdmsEnv(r.data?.fdms_env ?? null))
      .catch(() => setFdmsEnv(null));
  }, []);

  if (fdmsEnv !== "TEST") return null;

  return (
    <div
      className="flex items-center justify-center gap-2 py-2 px-4 bg-amber-500 text-amber-950 text-sm font-medium"
      role="alert"
    >
      <span className="font-semibold">WARNING:</span>
      <span>FDMS running in TEST environment</span>
    </div>
  );
}
