// ---------------------------------------------------------------------------
// Types mirror the FastAPI backend's Pydantic schemas exactly, including a
// subtlety that matters: Decimal fields (price, price_paid) are serialized
// by Pydantic as JSON STRINGS (e.g. "100.00"), not numbers — while plain
// `float` fields (admin dashboard totals) come through as real numbers.
// UI code must parseFloat() any `price` / `price_paid` field before doing
// math or formatting with it.
// ---------------------------------------------------------------------------

export type UserRole = "buyer" | "seller" | "admin";

export interface User {
  id: number;
  email: string;
  role: UserRole;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface Venue {
  id: number;
  name: string;
  svg_layout_config?: Record<string, unknown> | null;
  total_capacity: number;
  created_at: string;
}

export type SeatCategory = "VIP" | "VVIP" | "NORMAL";

export interface Seat {
  id: number;
  venue_id: number;
  category: SeatCategory;
  row_number: number;
  seat_number: string;
}

export interface TicketPrice {
  id: number;
  event_id: number;
  section: SeatCategory;
  price: string; // Decimal -> JSON string
}

export interface EventItem {
  id: number;
  venue_id: number;
  title: string;
  description?: string | null;
  start_time: string;
  created_at: string;
  ticket_prices: TicketPrice[];
}

export interface EventVenue extends EventItem {
  venue: Venue;
}

export type SeatStatus = "AVAILABLE" | "HELD" | "CONFIRMED" | "CANCELLED";

export interface SeatStatusItem {
  seat_id: number;
  row_number: number;
  seat_number: string;
  category: SeatCategory;
  price: string; // Decimal -> JSON string
  status: SeatStatus;
  ticket_id: number | null;
  is_mine: boolean;
}

export interface EventSeatMap {
  event_id: number;
  seats: SeatStatusItem[];
}

export type TicketStatus = "HELD" | "CONFIRMED" | "CANCELLED";

export interface Ticket {
  id: number;
  event_id: number;
  user_id: number;
  seat_id: number;
  status: TicketStatus;
  price_paid: string; // Decimal -> JSON string
  created_at: string;
  seat?: Seat | null;
}

export interface CheckoutInitiateResponse {
  ticket_id: number;
  payment_token: string;
  confirm_url: string;
  qr_code_base64: string;
}

export interface EventRevenueRow {
  event_id: number;
  event_title: string;
  tickets_sold: number;
  revenue: number; // plain float, NOT a Decimal string
}

export interface AdminDashboard {
  total_revenue: number; // plain float
  total_tickets_sold: number;
  active_holds: number;
  revenue_per_event: EventRevenueRow[];
}

// ---------------------------------------------------------------------------
// WebSocket protocol types
// ---------------------------------------------------------------------------

export interface WSConnected {
  event: "CONNECTED";
  message: string;
  user_id: number;
}
export interface WSSeatHeld {
  event: "SEAT_HELD";
  seat_id: number;
  ticket_id: number;
  held_by_user_id: number;
  status: "HELD";
}
export interface WSSeatReleased {
  event: "SEAT_RELEASED";
  seat_id: number;
  status: "CANCELLED";
  reason?: string;
}
export interface WSSeatConfirmed {
  event: "SEAT_CONFIRMED";
  seat_id: number;
  ticket_id: number;
  buyer_id: number;
  status: "CONFIRMED";
}
export interface WSSoldOut {
  event: "EVENT_SOLD_OUT";
  message: string;
}
export interface WSErrorMsg {
  event: "ERROR";
  message: string;
}

export type WSInboundMessage =
  | WSConnected
  | WSSeatHeld
  | WSSeatReleased
  | WSSeatConfirmed
  | WSSoldOut
  | WSErrorMsg;
