"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { checkoutTicket, ApiError } from "@/lib/api";
import type { CheckoutInitiateResponse } from "@/types";

export default function CheckoutPage() {
  const params = useParams<{ id: string }>();
  const ticketId = Number(params.id);

  const [checkout, setCheckout] = useState<CheckoutInitiateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(ticketId)) return;
    checkoutTicket(ticketId)
      .then(setCheckout)
      .catch((err) => {
        const message =
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : "Could not start checkout for this ticket.";
        setError(message);
      })
      .finally(() => setLoading(false));
  }, [ticketId]);

  const handleSimulateScan = () => {
    if (!checkout) return;
    // "Scanning" the QR is just visiting the confirm_url — the backend
    // treats hitting that URL as the payment-success signal. Opening it in
    // a new tab keeps this checkout page (and its QR) visible.
    window.open(checkout.confirm_url, "_blank", "noopener,noreferrer");
    setConfirmed(true);
  };

  if (loading) return <p className="text-slate-400">Preparing checkout...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!checkout) return null;

  return (
    <div className="mx-auto max-w-md">
      <div className="card flex flex-col items-center text-center">
        <h1 className="text-xl font-bold text-white">Complete your payment</h1>
        <p className="mt-1 text-sm text-slate-400">Ticket #{checkout.ticket_id}</p>

        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={checkout.qr_code_base64}
          alt="Payment QR code"
          className="mt-6 h-56 w-56 rounded-lg bg-white p-3"
        />

        <p className="mt-4 text-xs text-slate-500">
          Scan this QR with a phone camera, or click below to simulate a scan.
        </p>

        <button onClick={handleSimulateScan} className="btn-primary mt-6 w-full">
          Simulate Payment (Open Confirm Link)
        </button>

        {confirmed && (
          <p className="mt-4 text-sm text-emerald-400">
            Payment link opened in a new tab — once confirmed there, your seat map will update
            live.
          </p>
        )}

        <a
          href={checkout.confirm_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 break-all text-xs text-slate-500 underline"
        >
          {checkout.confirm_url}
        </a>
      </div>
    </div>
  );
}
