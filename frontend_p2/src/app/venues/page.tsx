"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getVenues } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { Venue } from "@/types";

export default function VenuesPage() {
  const role = useAuthStore((s) => s.role);
  const canManage = role === "seller" || role === "admin";

  const [venues, setVenues] = useState<Venue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVenues()
      .then(setVenues)
      .catch(() => setError("Could not load venues."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-slate-400">Loading venues...</p>;
  if (error) return <p className="text-red-400">{error}</p>;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Venues</h1>
        {canManage && (
          <Link href="/venues/create" className="btn-primary">
            + New Venue
          </Link>
        )}
      </div>

      {venues.length === 0 ? (
        <p className="text-slate-400">No venues yet.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {venues.map((venue) => (
            <div key={venue.id} className="card">
              <h2 className="text-lg font-semibold text-white">{venue.name}</h2>
              <p className="mt-1 text-sm text-slate-400">Capacity: {venue.total_capacity}</p>
              {canManage && (
                <Link
                  href={`/venues/${venue.id}/seats`}
                  className="mt-4 inline-block text-sm text-brand-500 hover:underline"
                >
                  Manage seats →
                </Link>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}