"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createVenue, ApiError } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useToast } from "@/components/ui/Toast";

export default function CreateVenuePage() {
  const router = useRouter();
  const { token, role } = useAuthStore();
  const { showToast } = useToast();

  const [name, setName] = useState("");
  const [totalCapacity, setTotalCapacity] = useState(50);
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
      const venue = await createVenue({ name, total_capacity: totalCapacity });
      showToast("Venue created.", "success");
      router.push(`/venues/${venue.id}/seats`);
    } catch (err) {
      const message =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not create venue.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <div className="card">
        <h1 className="mb-6 text-xl font-bold text-white">Create a Venue</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Venue name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input"
              placeholder="Grand Arena"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Total capacity</label>
            <input
              type="number"
              min={1}
              required
              value={totalCapacity}
              onChange={(e) => setTotalCapacity(Number(e.target.value))}
              className="input"
            />
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button type="submit" disabled={loading} className="btn-primary mt-2">
            {loading ? "Creating..." : "Create venue"}
          </button>
        </form>
      </div>
    </div>
  );
}