import React, { memo } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

const options = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    title: { display: true, text: "Sales by Currency" },
  },
  scales: {
    y: { beginAtZero: true },
  },
};

function SalesVolumeChart({ sales = {} }) {
  const labels = Object.keys(sales) || [];
  const data = Object.values(sales) || [];

  const chartData = {
    labels,
    datasets: [
      {
        label: "Amount",
        data,
        backgroundColor: ["rgba(79, 70, 229, 0.7)", "rgba(6, 182, 212, 0.7)"],
        borderColor: ["rgb(79, 70, 229)", "rgb(6, 182, 212)"],
        borderWidth: 1,
      },
    ],
  };

  if (!labels.length) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500 bg-white rounded-lg shadow-md p-4">
        No sales data
      </div>
    );
  }

  return (
    <div className="h-64">
      <Bar options={options} data={chartData} />
    </div>
  );
}

export default memo(SalesVolumeChart);
