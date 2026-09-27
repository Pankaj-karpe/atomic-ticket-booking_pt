"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createSeatsBulk, ApiError } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useToast } from "@/components/ui/Toast";
import type { SeatCategory } from "@/types";

interface SeatRow {
  category: SeatCategory;
  row_number: number;
  seat_number: string;
}

export default function ManageSeatsPage() {
  const params = useParams<{ id: string }>();
  const venueId = Number(params.id);
  const router = useRouter();
  const { token, role } = useAuthStore();
  const { showToast } = useToast();

  const [rows, setRows] = useState<SeatRow[]>([
    { category: "NORMAL", row_number: 1, seat_number: "A1" },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!token) {
    router.push("/login");
    return null;
  }
  if (role !== "seller" && role !== "admin") {
    return <p className="text-red-400">Seller or admin access required.</p>;
  }

  const updateRow = (index: number, patch: Partial<SeatRow>) =>
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const addRow = () =>
    setRows((prev) => [...prev, { category: "NORMAL", row_number: 1, seat_number: "" }]);

  const removeRow = (index: number) =>
    setRows((prev) => prev.filter((_, i) => i !== index));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await createSeatsBulk(venueId, rows);
      showToast(`${rows.length} seat(s) created.`, "success");
      router.push("/venues");
    } catch (err) {
      const message =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not create seats.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="card">
        <h1 className="mb-6 text-xl font-bold text-white">Add Seats to Venue #{venueId}</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {rows.map((row, i) => (
            <div key={i} className="flex items-end gap-2">
              <div>
                <label className="mb-1 block text-xs text-slate-400">Category</label>
                <select
                  value={row.category}
                  onChange={(e) => updateRow(i, { category: e.target.value as SeatCategory })}
                  className="input"
                >
                  <option value="NORMAL">NORMAL</option>
                  <option value="VIP">VIP</option>
                  <option value="VVIP">VVIP</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">Row</label>
                <input
                  type="number"
                  min={1}
                  value={row.row_number}
                  onChange={(e) => updateRow(i, { row_number: Number(e.target.value) })}
                  className="input w-20"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">Seat number</label>
                <input
                  value={row.seat_number}
                  onChange={(e) => updateRow(i, { seat_number: e.target.value })}
                  className="input w-24"
                  placeholder="A1"
                />
              </div>
              {rows.length > 1 && (
                <button type="button" onClick={() => removeRow(i)} className="btn-secondary py-2 text-xs">
                  Remove
                </button>
              )}
            </div>
          ))}

          <button type="button" onClick={addRow} className="btn-secondary self-start text-xs">
            + Add another seat
          </button>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button type="submit" disabled={loading} className="btn-primary mt-2">
            {loading ? "Saving..." : `Create ${rows.length} seat(s)`}
          </button>
        </form>
      </div>
    </div>
  );
}