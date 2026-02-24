import React, { memo } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const options = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    title: { display: true, text: "Receipts per Hour (Today)" },
  },
  scales: {
    x: { title: { display: true, text: "Hour" } },
    y: { beginAtZero: true },
  },
};

function ReceiptsTrendChart({ receiptsPerHour = [] }) {
  const labels = receiptsPerHour.map((d) => `${d.hour}:00`) || [];
  const data = receiptsPerHour.map((d) => d.count) || [];

  const chartData = {
    labels,
    datasets: [
      {
        label: "Receipts",
        data,
        borderColor: "rgb(79, 70, 229)",
        backgroundColor: "rgba(79, 70, 229, 0.1)",
        tension: 0.3,
      },
    ],
  };

  return (
    <div className="h-64">
      <Line options={options} data={chartData} />
    </div>
  );
}

export default memo(ReceiptsTrendChart);
