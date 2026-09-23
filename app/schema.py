

from pydantic import BaseModel, EmailStr, ConfigDict, Field
from datetime import datetime
from typing import Optional, List, Any , Literal
from decimal import Decimal
 
# Base Config to enable ORM mode across all schemas
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
 
# ==========================================
# 1. USER SCHEMAS
# ==========================================
class UserBase(BaseModel):
    email: EmailStr
 
class UserCreate(UserBase):
    password: str
    role: Literal["buyer", "seller", "admin"]
 
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[Literal["buyer", "seller", "admin"]] = None
 
class UserResponse(UserBase, ORMBase):
    id: int
    role: str
    created_at: datetime
 
 
# ==========================================
# 2. SEAT SCHEMAS
# ==========================================
class SeatBase(BaseModel):
    category: Literal["VIP", "VVIP", "NORMAL"]
    row_number: int = Field(gt=0)
    seat_number: str
 
class SeatCreate(SeatBase):
    venue_id: int
 
class SeatBulkCreate(BaseModel):
    """For seeding a venue's whole layout in one call — e.g. every seat in
    a row, or an entire section — instead of one HTTP call per seat."""
    seats: List[SeatBase]
 
class SeatUpdate(BaseModel):
    category: Optional[Literal["VIP", "VVIP", "NORMAL"]] = None
    row_number: Optional[int] = Field(default=None, gt=0)
    seat_number: Optional[str] = None
 
class SeatResponse(SeatBase, ORMBase):
    id: int
    venue_id: int
 
class SeatStatusResponse(SeatBase):
    seat_id: int
    price: Decimal = Field(..., max_digits=10, decimal_places=2)
    status: Literal["AVAILABLE", "HELD", "CONFIRMED", "CANCELLED"]
    ticket_id: Optional[int] = None
    is_mine: bool = False
 
 
# ==========================================
# 3. VENUE SCHEMAS
# ==========================================
class VenueBase(BaseModel):
    name: str
    svg_layout_config: Optional[dict[str, Any]] = None
    total_capacity: int = Field(default=50, gt=0)
 
class VenueCreate(VenueBase):
    pass
 
class VenueUpdate(BaseModel):
    name: Optional[str] = None
    svg_layout_config: Optional[dict[str, Any]] = None
    total_capacity: Optional[int] = Field(default=None, gt=0)
 
class VenueResponse(VenueBase, ORMBase):
    id: int
    created_at: datetime
 
 
# ==========================================
# 4. TICKET PRICE SCHEMAS
# ==========================================
class TicketPriceBase(BaseModel):
    section: Literal["VIP", "VVIP", "NORMAL"]
    price: Decimal = Field(..., max_digits=10, decimal_places=2)
 
class TicketPriceCreate(TicketPriceBase):
    event_id: int
 
class TicketPriceUpdate(BaseModel):
    section: Optional[Literal["VIP", "VVIP", "NORMAL"]] = None
    price: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2, ge=0)
 
class TicketPriceResponse(TicketPriceBase, ORMBase):
    id: int
    event_id: int
 
 
# ==========================================
# 5. EVENT SCHEMAS
# ==========================================
class EventBase(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    start_time: datetime
 
class EventCreate(EventBase):
    venue_id: int
 
class EventUpdate(BaseModel):
    venue_id: Optional[int] = None
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
 
class EventResponse(EventBase, ORMBase):
    id: int
    venue_id: int
    created_at: datetime
    ticket_prices: List[TicketPriceResponse] = []
 
class EventVenueResponse(EventBase, ORMBase):
    id: int
    venue_id: int
    created_at: datetime
    venue: VenueBase
    ticket_prices: List[TicketPriceResponse] = []
 
class EventRevenueResponse(BaseModel):
    event_id: int
    event_title: str
    tickets_sold: int
    revenue: float
 
class EventSeatMapResponse(BaseModel):
    event_id: int
    seats: List[SeatStatusResponse]
 
 
# ==========================================
# 6. TICKET / RESERVATION SCHEMAS
# ==========================================
class SeatHoldRequest(BaseModel):
    """Payload sent by client when clicking a seat on the SVG map"""
    seat_id: int
 
class TicketCreate(BaseModel):
    event_id: int
    seat_id: int
    price_paid: Decimal = Field(..., max_digits=10, decimal_places=2)
 
class TicketStatusUpdate(BaseModel):
    status: Literal["HELD", "CONFIRMED", "CANCELLED"]
 
class TicketResponse(ORMBase):
    id: int
    event_id: int
    user_id: int
    seat_id: int
    status: str
    price_paid: Decimal
    created_at: datetime
    seat: Optional[SeatResponse] = None
 
class TicketCheckoutRequest(BaseModel):
    ticket_id: int
 
 
# ==========================================
# 7. TOKEN
# ==========================================
class TokenData(BaseModel):
    id: Optional[str] = None
 
 
# ==========================================
# 8. ADMIN
# ==========================================
class AdminDashboardResponse(BaseModel):
    total_revenue: float
    total_tickets_sold: int
    active_holds: int
    revenue_per_event: List[EventRevenueResponse]
 
 
# ==========================================
# 9. PAYMENT INTENT
# ==========================================
class CheckoutInitiateResponse(BaseModel):
    """Returned by POST /orders/checkout — the ticket is NOT confirmed yet,
    this just hands back the QR/link the 'payment' happens through."""
    ticket_id: int
    payment_token: str
    confirm_url: str            # for manual testing — hit this in a browser/Postman to simulate a scan
    qr_code_base64: str         # data: URI you can drop straight into an <img src="...">
 
 
class PaymentConfirmResponse(BaseModel):
    ticket_id: int
    status: str
    message: str
