from .database import Base
from sqlalchemy.sql import func
from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship


###################################### USER ######################################
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_pwd = Column(String, nullable=False)
    role = Column(String, nullable=False, default="buyer", server_default="buyer")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    # Relationship
    tickets = relationship("Ticket", back_populates="user")


###################################### Venue ######################################
class Venue(Base):
    __tablename__ = "venues"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    svg_layout_config = Column(JSONB, nullable=True)
    total_capacity = Column(Integer, nullable=False, default=50)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationship
    events = relationship("Event", back_populates="venue", cascade="all, delete-orphan")
    seats = relationship("Seat", back_populates="venue", cascade="all, delete-orphan")


###################################### Event ######################################
class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationship
    venue = relationship("Venue", back_populates="events")
    ticket_prices = relationship("Ticket_Price", back_populates="event", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="event", cascade="all, delete-orphan")


###################################### Seat ######################################
class Seat(Base):
    __tablename__ = "seats"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    category = Column(String, nullable=False) #VIP, VVIP, NORMAL
    row_number = Column(Integer, nullable=False)
    seat_number = Column(String, nullable=False)

    # Composite Unique Constraint: Prevent duplicate seat coordinates inside the same venue
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "category",
            "row_number",
            "seat_number",
            name="uq_venue_seat",
        ),
    )

    # Relationship
    tickets = relationship("Ticket", back_populates="seat")
    venue = relationship("Venue", back_populates="seats")


###################################### Ticket_Price ######################################
class Ticket_Price(Base):
    __tablename__ = "ticket_prices"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    section = Column(String, nullable=False) # e.g., "VIP", "NORMAL"
    price = Column(Numeric(10, 2), nullable=False)

    # Composite Unique Constraint: An event can only have one price entry per section
    __table_args__ = (
        UniqueConstraint("event_id", "section", name="uq_event_section_price"),
    )

    # Relationships
    event = relationship("Event", back_populates="ticket_prices")


###################################### Ticket ######################################
class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="HELD") # HELD, CONFIRMED, CANCELLED
    price_paid = Column(Numeric(10, 2), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Composite Unique Constraint: Absolute DB-level backstop against double booking the same seat for an event
    __table_args__ = (
        UniqueConstraint("event_id", "seat_id", name="uq_event_seat_ticket"),
    )

    # Relationships
    event = relationship("Event", back_populates="tickets")
    user = relationship("User", back_populates="tickets")
    seat = relationship("Seat", back_populates="tickets")


###################################### Payment Intent ######################################
class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, unique=True)
    token = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationship
    ticket = relationship("Ticket")