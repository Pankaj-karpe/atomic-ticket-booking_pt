"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { getEventSeatMap } from "@/lib/api";
import type { EventSeatMap, SeatStatusItem, WSInboundMessage } from "@/types";

type ConnectionState = "idle" | "connecting" | "connected" | "closed" | "error";

interface UseSeatMapSocketResult {
  seats: SeatStatusItem[];
  connectionState: ConnectionState;
  holdSeat: (seatId: number) => void;
  releaseSeat: (seatId: number) => void;
  refreshSeatMap: () => Promise<void>;
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8000";

export function useSeatMapSocket(
  eventId: number,
  onMessage?: (msg: WSInboundMessage) => void
): UseSeatMapSocketResult {
  const token = useAuthStore((s) => s.token);
  const [seats, setSeats] = useState<SeatStatusItem[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  // Fetch the current snapshot via REST first — this is what makes a
  // freshly loaded page (or a reconnect) show correct state immediately,
  // instead of a blank map until the first WebSocket broadcast arrives.
  const refreshSeatMap = useCallback(async () => {
    try {
      const data: EventSeatMap = await getEventSeatMap(eventId);
      setSeats(data.seats);
    } catch {
      // A failed snapshot fetch shouldn't crash the page — the WebSocket
      // will still deliver live updates once connected.
    }
  }, [eventId]);

  useEffect(() => {
    refreshSeatMap();
  }, [refreshSeatMap]);

  useEffect(() => {
    if (!token) {
      setConnectionState("idle");
      return;
    }

    setConnectionState("connecting");
    const ws = new WebSocket(`${WS_URL}/ws/events/${eventId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: "auth", token }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as WSInboundMessage;
      const myUserId = useAuthStore.getState().userId;

      if (msg.event === "CONNECTED") {
        setConnectionState("connected");
      }

      if (msg.event === "SEAT_HELD") {
        const isMine = msg.held_by_user_id === myUserId;
        setSeats((prev) =>
          prev.map((seat) =>
            seat.seat_id === msg.seat_id
              ? { ...seat, status: "HELD", ticket_id: isMine ? msg.ticket_id : null, is_mine: isMine }
              : seat
          )
        );
      }

      if (msg.event === "SEAT_RELEASED") {
        setSeats((prev) =>
          prev.map((seat) =>
            seat.seat_id === msg.seat_id
              ? { ...seat, status: "AVAILABLE", ticket_id: null, is_mine: false }
              : seat
          )
        );
      }

      if (msg.event === "SEAT_CONFIRMED") {
        const isMine = msg.buyer_id === myUserId;
        setSeats((prev) =>
          prev.map((seat) =>
            seat.seat_id === msg.seat_id
              ? { ...seat, status: "CONFIRMED", is_mine: isMine || seat.is_mine }
              : seat
          )
        );
      }

      onMessageRef.current?.(msg);
    };

    ws.onerror = () => setConnectionState("error");
    ws.onclose = () => setConnectionState((prev) => (prev === "error" ? prev : "closed"));

    return () => {
      ws.close();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId, token]);

  // NOTE: price_paid is intentionally NOT computed here — the backend
  // ignores whatever price the client sends and always looks up the real,
  // seller-configured price server-side. We still send a value because the
  // WebSocket message schema expects the field.
  const holdSeat = useCallback((seatId: number) => {
    wsRef.current?.send(JSON.stringify({ action: "hold_seat", seat_id: seatId, price_paid: 0 }));
  }, []);

  const releaseSeat = useCallback((seatId: number) => {
    wsRef.current?.send(JSON.stringify({ action: "release_seat", seat_id: seatId }));
  }, []);

  return { seats, connectionState, holdSeat, releaseSeat, refreshSeatMap };
}
