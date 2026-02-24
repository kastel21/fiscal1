import React, { memo } from "react";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { Doughnut } from "react-chartjs-2";

ChartJS.register(ArcElement, Tooltip, Legend);

const COLORS = ["#4f46e5", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];

function TaxBreakdownChart({ taxBreakdown = [] }) {
  const data = {
    labels: taxBreakdown.map((t) => t.band) || [],
    datasets: [
      {
        data: taxBreakdown.map((t) => t.amount) || [],
        backgroundColor: COLORS.slice(0, taxBreakdown.length),
        borderWidth: 2,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "right" },
      title: { display: true, text: "Tax Band Breakdown" },
    },
  };

  if (!taxBreakdown?.length) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500 bg-white rounded-lg shadow-md p-4">
        No tax data
      </div>
    );
  }

  return (
    <div className="h-64">
      <Doughnut data={data} options={options} />
    </div>
  );
}

export default memo(TaxBreakdownChart);
