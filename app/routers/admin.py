"""
Admin-only analytics endpoint.
 
GET /admin/dashboard
    Returns:
      - total_revenue: sum of price_paid across all CONFIRMED tickets
      - total_tickets_sold: count of CONFIRMED tickets
      - active_holds: count of tickets currently in HELD status
      - revenue_per_event: per-event breakdown of tickets sold + revenue
 
Restricted to users with role == "admin" via the require_admin dependency.
"""
from typing import List
from fastapi import FastAPI, APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import schema, oauth2, models, database


router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

# ==========================================
# get admin dashboard 
# ==========================================
@router.get("/dashboard", response_model=schema.AdminDashboardResponse)
def get_admin_dashboard(db: Session = Depends(database.get_db), current_user: models.User = Depends(oauth2.get_current_admin)):

    # total revenue and total_tickets_sold across all events
    totals = (
        db.query(func.coalesce(func.sum(models.Ticket.price_paid), 0).label("total_revenue"),
                func.count(models.Ticket.id).label("total_tickets_sold"),).
                filter(models.Ticket.status == "CONFIRMED").one()
    )

    # Active held tickets
    active_holds = (
        db.query(func.count(models.Ticket.id)).
        filter(models.Ticket.status == "HELD").scalar()
    )

    # REVENUE PER EVENT
    # 1. determining tickets_sold, revenue, event_title, event_id
    per_event_rows = (
        db.query(models.Event.id.label("event_id"),
                models.Event.title.label("event_title"),
                func.coalesce(func.sum(models.Ticket.price_paid), 0).label("revenue"),
                func.count(models.Ticket.id).label("tickets_sold"),
                )
            .join(models.Ticket, models.Ticket.event_id == models.Event.id)
            .filter(models.Ticket.status == "CONFIRMED")
            .group_by(models.Event.id, models.Event.title)
            .order_by(func.sum(models.Ticket.price_paid).desc())
            .all()
    )

    # 2. using the 1 logic on each event and convert in pydantic response model 
    revenue_per_event = [
        schema.EventRevenueResponse(
            event_id=row.event_id,
            event_title=row.event_title,
            tickets_sold=row.tickets_sold,
            revenue=float(row.revenue),
        )
        for row in per_event_rows
    ]

    # 3. return total_revenue, total_tickets_sold, active_holds, revenue_per_event to admin dashboard
    return schema.AdminDashboardResponse(
        total_revenue=float(totals.total_revenue),
        total_tickets_sold=totals.total_tickets_sold,
        active_holds=active_holds or 0,
        revenue_per_event=revenue_per_event,
    )