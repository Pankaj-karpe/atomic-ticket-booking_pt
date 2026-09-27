"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getEvents } from "@/lib/api";
import type { EventItem } from "@/types";

export default function EventsListPage() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvents()
      .then(setEvents)
      .catch(() => setError("Could not load events. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-slate-400">Loading events...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (events.length === 0) return <p className="text-slate-400">No events yet.</p>;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Upcoming Events</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {events.map((event) => (
          <Link
            key={event.id}
            href={`/events/${event.id}`}
            className="card block transition-colors hover:border-brand-500"
          >
            <h2 className="text-lg font-semibold text-white">{event.title}</h2>
            {event.description && (
              <p className="mt-1 line-clamp-2 text-sm text-slate-400">{event.description}</p>
            )}
            <p className="mt-3 text-xs text-slate-500">
              {new Date(event.start_time).toLocaleString()}
            </p>
            {event.ticket_prices.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {event.ticket_prices.map((tp) => (
                  <span
                    key={tp.id}
                    className="rounded-full bg-slate-800 px-2 py-1 text-xs text-slate-300"
                  >
                    {tp.section}: ₹{parseFloat(tp.price).toFixed(2)}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
