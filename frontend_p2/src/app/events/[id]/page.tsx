"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getEvent } from "@/lib/api";
import { useSeatMapSocket } from "@/hooks/useSeatMapSocket";
import { useAuthStore } from "@/store/authStore";
import { useToast } from "@/components/ui/Toast";
import type { EventItem, SeatStatusItem, WSInboundMessage } from "@/types";

const STATUS_CLASSES: Record<SeatStatusItem["status"], string> = {
  AVAILABLE: "bg-emerald-600 text-white",
  HELD: "bg-amber-500 text-black",
  CONFIRMED: "bg-slate-600 text-slate-300",
  CANCELLED: "bg-emerald-600 text-white",
};

export default function EventDetailPage() {
  const params = useParams<{ id: string }>();
  const eventId = Number(params.id);
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const { showToast } = useToast();

  const [event, setEvent] = useState<EventItem | null>(null);
  const [loadingEvent, setLoadingEvent] = useState(true);

  const handleWsMessage = (msg: WSInboundMessage) => {
    if (msg.event === "SEAT_HELD") showToast(`Seat ${msg.seat_id} was just held.`, "info");
    if (msg.event === "SEAT_RELEASED") showToast(`Seat ${msg.seat_id} is available again.`, "info");
    if (msg.event === "SEAT_CONFIRMED") showToast(`Seat ${msg.seat_id} confirmed!`, "success");
    if (msg.event === "EVENT_SOLD_OUT") showToast(msg.message, "info");
    if (msg.event === "ERROR") showToast(msg.message, "error");
  };

  const { seats, connectionState, holdSeat, releaseSeat } = useSeatMapSocket(
    eventId,
    handleWsMessage
  );

  useEffect(() => {
    if (!Number.isFinite(eventId)) return;
    getEvent(eventId)
      .then(setEvent)
      .finally(() => setLoadingEvent(false));
  }, [eventId]);

  const seatsByRow = useMemo(() => {
    const grouped = new Map<number, SeatStatusItem[]>();
    for (const seat of seats) {
      const row = grouped.get(seat.row_number) ?? [];
      row.push(seat);
      grouped.set(seat.row_number, row);
    }
    return [...grouped.entries()].sort(([a], [b]) => a - b);
  }, [seats]);

  const handleSeatClick = (seat: SeatStatusItem) => {
    if (!token) {
      showToast("Log in to hold a seat.", "error");
      return;
    }
    if (seat.status === "AVAILABLE") {
      holdSeat(seat.seat_id);
    } else if (seat.status === "HELD" && seat.is_mine) {
      releaseSeat(seat.seat_id);
    }
  };

  if (loadingEvent) return <p className="text-slate-400">Loading event...</p>;
  if (!event) return <p className="text-red-400">Event not found.</p>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">{event.title}</h1>
        {event.description && <p className="mt-1 text-slate-400">{event.description}</p>}
        <p className="mt-1 text-sm text-slate-500">
          {new Date(event.start_time).toLocaleString()}
        </p>
        <p className="mt-2 text-xs">
          Live connection:{" "}
          <span
            className={
              connectionState === "connected"
                ? "text-emerald-400"
                : connectionState === "connecting"
                  ? "text-amber-400"
                  : "text-slate-500"
            }
          >
            {connectionState}
          </span>
        </p>
        {!token && (
          <p className="mt-2 text-sm text-amber-400">
            <Link href="/login" className="underline">
              Log in
            </Link>{" "}
            to hold a seat.
          </p>
        )}
      </div>

      <div className="mb-6 flex gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <span className="h-3 w-3 rounded bg-emerald-600" /> Available
        </span>
        <span className="flex items-center gap-1">
          <span className="h-3 w-3 rounded bg-amber-500" /> Held
        </span>
        <span className="flex items-center gap-1">
          <span className="h-3 w-3 rounded bg-brand-600" /> Your seat
        </span>
        <span className="flex items-center gap-1">
          <span className="h-3 w-3 rounded bg-slate-600" /> Confirmed
        </span>
      </div>

      <div className="card flex flex-col gap-3">
        {seatsByRow.length === 0 && <p className="text-slate-400">No seats configured yet.</p>}
        {seatsByRow.map(([rowNumber, rowSeats]) => (
          <div key={rowNumber} className="flex items-center gap-3">
            <span className="w-6 text-xs text-slate-500">R{rowNumber}</span>
            <div className="flex flex-wrap gap-2">
              {rowSeats
                .sort((a, b) => a.seat_number.localeCompare(b.seat_number))
                .map((seat) => {
                  const isMine = seat.is_mine;
                  const clickable =
                    seat.status === "AVAILABLE" || (seat.status === "HELD" && isMine);
                  return (
                    <button
                      key={seat.seat_id}
                      disabled={!clickable}
                      onClick={() => handleSeatClick(seat)}
                      title={`${seat.seat_number} · ${seat.category} · ₹${parseFloat(seat.price).toFixed(2)}`}
                      className={`seat-btn ${isMine ? "bg-brand-600 text-white ring-2 ring-brand-300" : STATUS_CLASSES[seat.status]}`}
                    >
                      {seat.seat_number}
                    </button>
                  );
                })}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        {seats
          .filter((s) => s.is_mine && s.status === "HELD" && s.ticket_id)
          .map((s) => (
            <button
              key={s.seat_id}
              onClick={() => router.push(`/checkout/${s.ticket_id}`)}
              className="btn-primary"
            >
              Checkout seat {s.seat_number} (₹{parseFloat(s.price).toFixed(2)})
            </button>
          ))}
      </div>
    </div>
  );
}
