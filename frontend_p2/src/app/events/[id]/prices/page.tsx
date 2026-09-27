"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createTicketPrice, ApiError } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useToast } from "@/components/ui/Toast";
import type { SeatCategory } from "@/types";

export default function EventPricesPage() {
  const params = useParams<{ id: string }>();
  const eventId = Number(params.id);
  const router = useRouter();
  const { token, role } = useAuthStore();
  const { showToast } = useToast();

  const [section, setSection] = useState<SeatCategory>("NORMAL");
  const [price, setPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setLoading(true);
    try {
      await createTicketPrice(eventId, { section, price });
      showToast(`Price for ${section} saved.`, "success");
      setPrice("");
    } catch (err) {
      const message =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not save price.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <div className="card">
        <h1 className="mb-2 text-xl font-bold text-white">Set Ticket Prices</h1>
        <p className="mb-6 text-sm text-slate-400">Event #{eventId}</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Section</label>
            <select
              value={section}
              onChange={(e) => setSection(e.target.value as SeatCategory)}
              className="input"
            >
              <option value="NORMAL">NORMAL</option>
              <option value="VIP">VIP</option>
              <option value="VVIP">VVIP</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Price (₹)</label>
            <input
              required
              inputMode="decimal"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="input"
              placeholder="499.00"
            />
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button type="submit" disabled={loading} className="btn-primary mt-2">
            {loading ? "Saving..." : "Save price"}
          </button>
        </form>

        <a href={`/events/${eventId}`} className="mt-6 inline-block text-sm text-brand-500 hover:underline">
          Go to event page →
        </a>
      </div>
    </div>
  );
}