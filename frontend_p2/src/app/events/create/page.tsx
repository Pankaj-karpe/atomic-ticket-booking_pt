"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createEvent, getVenues, ApiError } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useToast } from "@/components/ui/Toast";
import type { Venue } from "@/types";

export default function CreateEventPage() {
  const router = useRouter();
  const { token, role } = useAuthStore();
  const { showToast } = useToast();

  const [venues, setVenues] = useState<Venue[]>([]);
  const [venueId, setVenueId] = useState<number | "">("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startTime, setStartTime] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVenues().then(setVenues).catch(() => setVenues([]));
  }, []);

  if (!token) {
    router.push("/login");
    return null;
  }
  if (role !== "seller" && role !== "admin") {
    return <p className="text-red-400">Seller or admin access required.</p>;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!venueId) {
      setError("Select a venue.");
      return;
    }
    setLoading(true);
    try {
      const event = await createEvent({
        venue_id: Number(venueId),
        title,
        description: description || null,
        start_time: new Date(startTime).toISOString(),
      });
      showToast("Event created.", "success");
      router.push(`/events/${event.id}/prices`);
    } catch (err) {
      const message =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not create event.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <div className="card">
        <h1 className="mb-6 text-xl font-bold text-white">Create an Event</h1>
        {venues.length === 0 ? (
          <p className="text-amber-400">
            No venues exist yet —{" "}
            <a href="/venues/create" className="underline">
              create one first
            </a>
            .
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Venue</label>
              <select
                required
                value={venueId}
                onChange={(e) => setVenueId(Number(e.target.value))}
                className="input"
              >
                <option value="">Select a venue</option>
                {venues.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Title</label>
              <input required value={title} onChange={(e) => setTitle(e.target.value)} className="input" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Description</label>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="input"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Start time</label>
              <input
                type="datetime-local"
                required
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="input"
              />
            </div>

            {error && <p className="text-sm text-red-400">{error}</p>}

            <button type="submit" disabled={loading} className="btn-primary mt-2">
              {loading ? "Creating..." : "Create event"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}