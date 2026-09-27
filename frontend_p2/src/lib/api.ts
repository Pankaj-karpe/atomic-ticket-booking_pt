import { useAuthStore } from "@/store/authStore";
import type {
  AdminDashboard,
  AuthResponse,
  CheckoutInitiateResponse,
  EventItem,
  EventSeatMap,
  EventVenue,
  Seat,
  SeatCategory,
  Ticket,
  TicketPrice,
  User,
  UserRole,
  Venue,
} from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.status = status;
    this.detail = detail;
  }
}

function authHeader(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* response wasn't JSON */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

// ---------------------------------------------------------------------------
// AUTH
// ---------------------------------------------------------------------------
export async function signup(email: string, password: string, role: UserRole): Promise<User> {
  return request<User>("/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
  });
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  // /login is OAuth2PasswordRequestForm on the backend -> form-encoded body,
  // NOT JSON. This is the one call that can't go through request().
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);

  const res = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const parsed = await res.json();
      detail = parsed.detail ?? parsed;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as AuthResponse;
}

// ---------------------------------------------------------------------------
// EVENTS
// ---------------------------------------------------------------------------
export async function getEvents(): Promise<EventItem[]> {
  return request<EventItem[]>("/events/");
}

export async function getEvent(id: number): Promise<EventItem> {
  return request<EventItem>(`/events/${id}`);
}

export async function getEventLayout(id: number): Promise<EventVenue> {
  return request<EventVenue>(`/events/${id}/layout`);
}

export async function getEventSeatMap(id: number): Promise<EventSeatMap> {
  return request<EventSeatMap>(`/events/${id}/seats`);
}

export async function createEvent(payload: {
  venue_id: number;
  title: string;
  description?: string | null;
  start_time: string;
}): Promise<EventItem> {
  return request<EventItem>("/events/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createTicketPrice(
  eventId: number,
  payload: { section: SeatCategory; price: string }
): Promise<TicketPrice> {
  return request<TicketPrice>(`/events/${eventId}/prices`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// VENUES
// ---------------------------------------------------------------------------
export async function getVenues(): Promise<Venue[]> {
  return request<Venue[]>("/venues/");
}

export async function createVenue(payload: {
  name: string;
  svg_layout_config?: Record<string, unknown> | null;
  total_capacity: number;
}): Promise<Venue> {
  return request<Venue>("/venues/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getVenue(id: number): Promise<Venue> {
  return request<Venue>(`/venues/${id}`);
}

export async function createSeatsBulk(
  venueId: number,
  seats: { category: SeatCategory; row_number: number; seat_number: string }[]
): Promise<Seat[]> {
  return request<Seat[]>(`/venues/${venueId}/seats/bulk`, {
    method: "POST",
    body: JSON.stringify({ seats }),
  });
}

export async function getVenueSeats(venueId: number): Promise<Seat[]> {
  return request<Seat[]>(`/venues/${venueId}/seats`);
}

// ---------------------------------------------------------------------------
// ORDERS
// ---------------------------------------------------------------------------
export async function getMyTickets(): Promise<Ticket[]> {
  return request<Ticket[]>("/orders/");
}

export async function getTicket(id: number): Promise<Ticket> {
  return request<Ticket>(`/orders/${id}`);
}

export async function checkoutTicket(ticketId: number): Promise<CheckoutInitiateResponse> {
  return request<CheckoutInitiateResponse>("/orders/checkout", {
    method: "POST",
    body: JSON.stringify({ ticket_id: ticketId }),
  });
}

export async function cancelTicket(id: number): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/orders/${id}/cancel`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// ADMIN
// ---------------------------------------------------------------------------
export async function getAdminDashboard(): Promise<AdminDashboard> {
  return request<AdminDashboard>("/admin/dashboard");
}
