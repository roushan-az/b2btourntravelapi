"""Admin Analytics & Stats Router."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, Destination, Hotel, Quotation, QuotationStatus, User, UserRole, Vehicle
from app.services.auth_service import get_current_admin

router = APIRouter(prefix="/admin/stats", tags=["Admin Analytics"])


@router.get("/overview")
async def overview_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    today = date.today()
    month_start = today.replace(day=1)

    total_agents = await db.execute(select(func.count()).where(User.role == UserRole.AGENT))
    active_agents = await db.execute(select(func.count()).where(User.role == UserRole.AGENT, User.is_active == True))
    total_quotations = await db.execute(select(func.count()).select_from(Quotation))
    month_quotations = await db.execute(
        select(func.count()).where(Quotation.created_at >= month_start.isoformat())
    )
    total_revenue = await db.execute(
        select(func.sum(Quotation.total_cost)).where(Quotation.status == QuotationStatus.CONFIRMED)
    )
    month_revenue = await db.execute(
        select(func.sum(Quotation.total_cost)).where(
            Quotation.status == QuotationStatus.CONFIRMED,
            Quotation.created_at >= month_start.isoformat(),
        )
    )
    pending_quotations = await db.execute(
        select(func.count()).where(Quotation.status.in_([QuotationStatus.SENT, QuotationStatus.PENDING]))
    )
    total_destinations = await db.execute(select(func.count()).select_from(Destination).where(Destination.is_active == True))
    total_hotels = await db.execute(select(func.count()).select_from(Hotel).where(Hotel.is_active == True))
    total_vehicles = await db.execute(select(func.count()).select_from(Vehicle).where(Vehicle.is_active == True))

    return {
        "agents": {
            "total": total_agents.scalar_one(),
            "active": active_agents.scalar_one(),
        },
        "quotations": {
            "total": total_quotations.scalar_one(),
            "this_month": month_quotations.scalar_one(),
            "pending": pending_quotations.scalar_one(),
        },
        "revenue": {
            "total": float(total_revenue.scalar_one() or 0),
            "this_month": float(month_revenue.scalar_one() or 0),
        },
        "catalog": {
            "destinations": total_destinations.scalar_one(),
            "hotels": total_hotels.scalar_one(),
            "vehicles": total_vehicles.scalar_one(),
        },
    }


@router.get("/top-agents")
async def top_agents(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(
            User.full_name,
            Agent.agency_name,
            func.count(Quotation.id).label("total_quotations"),
            func.sum(Quotation.total_cost).label("total_revenue"),
        )
        .join(Agent, Agent.user_id == User.id)
        .join(Quotation, Quotation.agent_user_id == User.id, isouter=True)
        .where(Quotation.status == QuotationStatus.CONFIRMED)
        .group_by(User.full_name, Agent.agency_name)
        .order_by(func.sum(Quotation.total_cost).desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "agent_name": r.full_name,
            "agency_name": r.agency_name,
            "total_quotations": r.total_quotations or 0,
            "total_revenue": float(r.total_revenue or 0),
        }
        for r in rows
    ]


@router.get("/quotation-trends")
async def quotation_trends(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """Daily quotation counts for the last N days."""
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(
            func.date(Quotation.created_at).label("day"),
            func.count().label("count"),
            func.sum(Quotation.total_cost).label("revenue"),
        )
        .where(Quotation.created_at >= since.isoformat())
        .group_by(func.date(Quotation.created_at))
        .order_by(func.date(Quotation.created_at))
    )
    return [
        {"date": str(r.day), "count": r.count, "revenue": float(r.revenue or 0)}
        for r in result.all()
    ]


@router.get("/status-breakdown")
async def status_breakdown(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(Quotation.status, func.count().label("count"))
        .group_by(Quotation.status)
    )
    return {r.status.value: r.count for r in result.all()}