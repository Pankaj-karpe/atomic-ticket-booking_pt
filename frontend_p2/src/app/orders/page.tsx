"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMyTickets, cancelTicket, ApiError } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useToast } from "@/components/ui/Toast";
import type { Ticket } from "@/types";

const STATUS_STYLES: Record<Ticket["status"], string> = {
  HELD: "bg-amber-500/20 text-amber-400",
  CONFIRMED: "bg-emerald-500/20 text-emerald-400",
  CANCELLED: "bg-slate-500/20 text-slate-400",
};

export default function OrdersPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const { showToast } = useToast();

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancellingId, setCancellingId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) {
      router.push("/login");
      return;
    }
    getMyTickets()
      .then(setTickets)
      .finally(() => setLoading(false));
  }, [token, router]);

  const handleCancel = async (id: number) => {
    setCancellingId(id);
    try {
      await cancelTicket(id);
      showToast("Ticket refunded and cancelled.", "success");
      setTickets((prev) =>
        prev.map((t) => (t.id === id ? { ...t, status: "CANCELLED" } : t))
      );
    } catch (err) {
      const message =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not cancel this ticket.";
      showToast(message, "error");
    } finally {
      setCancellingId(null);
    }
  };

  if (!token) return null;
  if (loading) return <p className="text-slate-400">Loading your orders...</p>;
  if (tickets.length === 0) return <p className="text-slate-400">You have no tickets yet.</p>;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">My Orders</h1>
      <div className="flex flex-col gap-3">
        {tickets.map((ticket) => (
          <div key={ticket.id} className="card flex items-center justify-between">
            <div>
              <p className="font-medium text-white">
                Ticket #{ticket.id} — Event #{ticket.event_id}
              </p>
              <p className="text-sm text-slate-400">
                Seat #{ticket.seat_id} · ₹{parseFloat(ticket.price_paid).toFixed(2)} · Booked{" "}
                {new Date(ticket.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`rounded-full px-3 py-1 text-xs font-medium ${STATUS_STYLES[ticket.status]}`}
              >
                {ticket.status}
              </span>
              {ticket.status === "CONFIRMED" && (
                <button
                  onClick={() => handleCancel(ticket.id)}
                  disabled={cancellingId === ticket.id}
                  className="btn-secondary py-1.5 text-xs"
                >
                  {cancellingId === ticket.id ? "Cancelling..." : "Cancel / Refund"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
