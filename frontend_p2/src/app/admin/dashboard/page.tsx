"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getAdminDashboard, ApiError } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { AdminDashboard } from "@/types";

export default function AdminDashboardPage() {
  const router = useRouter();
  const { token, role } = useAuthStore();

  const [data, setData] = useState<AdminDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      router.push("/login");
      return;
    }
    if (role !== "admin") {
      setError("Admin access required.");
      setLoading(false);
      return;
    }
    getAdminDashboard()
      .then(setData)
      .catch((err) => {
        const message =
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : "Could not load the dashboard.";
        setError(message);
      })
      .finally(() => setLoading(false));
  }, [token, role, router]);

  if (loading) return <p className="text-slate-400">Loading dashboard...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!data) return null;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Admin Dashboard</h1>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <p className="text-xs uppercase text-slate-500">Total Revenue</p>
          <p className="mt-2 text-3xl font-bold text-emerald-400">
            ₹{data.total_revenue.toFixed(2)}
          </p>
        </div>
        <div className="card">
          <p className="text-xs uppercase text-slate-500">Tickets Sold</p>
          <p className="mt-2 text-3xl font-bold text-white">{data.total_tickets_sold}</p>
        </div>
        <div className="card">
          <p className="text-xs uppercase text-slate-500">Active Holds</p>
          <p className="mt-2 text-3xl font-bold text-amber-400">{data.active_holds}</p>
        </div>
      </div>

      <h2 className="mb-3 mt-8 text-lg font-semibold text-white">Revenue per Event</h2>
      {data.revenue_per_event.length === 0 ? (
        <p className="text-slate-400">No confirmed sales yet.</p>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-slate-500">
              <tr>
                <th className="px-4 py-3">Event</th>
                <th className="px-4 py-3">Tickets Sold</th>
                <th className="px-4 py-3">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {data.revenue_per_event.map((row) => (
                <tr key={row.event_id} className="border-b border-slate-800/60">
                  <td className="px-4 py-3 text-white">{row.event_title}</td>
                  <td className="px-4 py-3 text-slate-300">{row.tickets_sold}</td>
                  <td className="px-4 py-3 text-emerald-400">₹{row.revenue.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
