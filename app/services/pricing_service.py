"""
Pricing Engine — Calculates package costs with seasonal rates,
agent markup, and GST. Used by both the package builder preview
and the final quotation creation.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import (
    Agent,
    Hotel,
    MealPlanCode,
    MealPlanRate,
    RoomType,
    Season,
    SeasonalPricingRule,
    User,
    Vehicle,
    VehicleSeasonalRate,
    Activity,
)

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _detect_season(travel_date: Optional[str]) -> Optional[Season]:
    """
    Detect the applicable season from a travel date string (YYYY-MM-DD).
    Returns None if date is not parseable.
    """
    if not travel_date:
        return None
    try:
        from datetime import date
        d = date.fromisoformat(travel_date)
        month = d.month
        # New Year window
        if (month == 12 and d.day >= 28) or (month == 1 and d.day <= 3):
            return Season.NEW_YEAR
        # Peak summer (April–June)
        if month in (4, 5, 6):
            return Season.PEAK
        # Regular summer (July–September)
        if month in (7, 8, 9):
            return Season.SUMMER
        # Autumn shoulder (October–November)
        if month in (10, 11):
            return Season.SUMMER  # Use summer rate for now
        # Winter (December–March)
        return Season.WINTER
    except ValueError:
        return None


class PricingEngine:
    """
    Core pricing calculations.
    All public methods return Decimal values rounded to 2 decimal places.
    """

    # ── Hotel pricing ─────────────────────────────────────────────────────────

    async def get_hotel_rate(
        self,
        db: AsyncSession,
        room_type_id: UUID,
        meal_plan: MealPlanCode,
        travel_date: Optional[str] = None,
    ) -> Decimal:
        """
        Return the per-night rate for a room type + meal plan,
        applying seasonal override if available.
        """
        season = _detect_season(travel_date)

        # Try seasonal rate first
        if season:
            from app.models import HotelSeasonalRate
            result = await db.execute(
                select(HotelSeasonalRate).where(
                    HotelSeasonalRate.room_type_id == room_type_id,
                    HotelSeasonalRate.season == season,
                    HotelSeasonalRate.meal_plan == meal_plan,
                )
            )
            seasonal = result.scalar_one_or_none()
            if seasonal:
                return _round(seasonal.rate_per_night)

        # Fall back to base rate
        result = await db.execute(
            select(MealPlanRate).where(
                MealPlanRate.room_type_id == room_type_id,
                MealPlanRate.meal_plan == meal_plan,
            )
        )
        base_rate = result.scalar_one_or_none()
        if not base_rate:
            logger.warning(f"No rate found for room_type={room_type_id} meal_plan={meal_plan}")
            return Decimal("0")

        # Apply global seasonal multiplier if no direct seasonal rate
        if season:
            result = await db.execute(
                select(SeasonalPricingRule).where(
                    SeasonalPricingRule.season == season,
                    SeasonalPricingRule.is_active == True,
                )
            )
            rule = result.scalar_one_or_none()
            if rule:
                return _round(base_rate.rate_per_night * rule.multiplier)

        return _round(base_rate.rate_per_night)

    # ── Vehicle pricing ───────────────────────────────────────────────────────

    async def get_vehicle_rate(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
        num_days: int,
        travel_date: Optional[str] = None,
    ) -> Decimal:
        """Return total vehicle cost for the package duration."""
        result = await db.execute(
            select(Vehicle)
            .options(selectinload(Vehicle.seasonal_rates))
            .where(Vehicle.id == vehicle_id, Vehicle.is_active == True)
        )
        vehicle = result.scalar_one_or_none()
        if not vehicle:
            return Decimal("0")

        base_per_day = vehicle.per_day_rate
        season = _detect_season(travel_date)
        surcharge = Decimal("0")

        if season:
            for sr in vehicle.seasonal_rates:
                if sr.season == season:
                    surcharge = sr.surcharge_per_day
                    break

        total = _round((base_per_day + surcharge) * num_days)
        return total

    # ── Activity pricing ──────────────────────────────────────────────────────

    async def get_activity_total(
        self,
        db: AsyncSession,
        activity_ids: List[UUID],
        num_adults: int = 2,
        num_children: int = 0,
    ) -> Decimal:
        if not activity_ids:
            return Decimal("0")
        result = await db.execute(
            select(Activity).where(Activity.id.in_(activity_ids), Activity.is_active == True)
        )
        activities = result.scalars().all()
        total = Decimal("0")
        for act in activities:
            adult_cost = act.base_price * num_adults
            child_rate = act.child_price if act.child_price is not None else act.base_price * Decimal("0.5")
            child_cost = child_rate * num_children
            total += adult_cost + child_cost
        return _round(total)

    # ── Markup ────────────────────────────────────────────────────────────────

    async def apply_agent_markup(
        self,
        db: AsyncSession,
        base_cost: Decimal,
        agent_user: User,
    ) -> Decimal:
        """Return the markup amount (not total — just the markup delta)."""
        agent = agent_user.agent_profile
        if not agent:
            # Admins building packages use 0 markup
            return Decimal("0")

        # FIX: Safely parse the markup_type as a string instead of relying on the deleted MarkupType enum
        markup_type_str = str(getattr(agent, 'markup_type', 'percentage')).lower()
        markup_value = getattr(agent, 'markup_value', Decimal("0"))

        if "percentage" in markup_type_str:
            markup = _round(base_cost * (markup_value / Decimal("100")))
        else:
            markup = _round(markup_value)

        return markup

    # ── GST ───────────────────────────────────────────────────────────────────

    def calculate_gst(self, amount: Decimal, rate: Optional[Decimal] = None) -> Decimal:
        gst_rate = rate if rate is not None else Decimal(str(settings.DEFAULT_GST_RATE))
        return _round(amount * (gst_rate / Decimal("100")))

    # ── Full package price ────────────────────────────────────────────────────

    async def calculate_package_price(
        self,
        db: AsyncSession,
        nights: int,
        num_days: int,
        hotel_selections: List[Dict],
        vehicle_id: Optional[UUID],
        activity_ids: List[UUID],
        agent_user: User,
        travel_date: Optional[str],
        num_adults: int = 2,
        num_children: int = 0,
    ) -> Dict:
        """
        Full package pricing. Returns a dict with all cost components.
        hotel_selections: [{"room_type_id": UUID, "meal_plan": str}, ...]
        """
        breakdown = []

        # ── Hotel costs ───────────────────────────────────────────────────────
        hotel_cost = Decimal("0")
        for sel in hotel_selections:
            room_type_id = UUID(str(sel["room_type_id"])) if not isinstance(sel["room_type_id"], UUID) else sel["room_type_id"]
            meal_plan = MealPlanCode(sel.get("meal_plan", "CP"))
            rate = await self.get_hotel_rate(db, room_type_id, meal_plan, travel_date)
            line_total = _round(rate * nights)
            hotel_cost += line_total

            # Fetch hotel name for breakdown
            rt_result = await db.execute(
                select(RoomType)
                .options(selectinload(RoomType.hotel).selectinload(Hotel.destination_rel))
                .where(RoomType.id == room_type_id)
            )
            rt = rt_result.scalar_one_or_none()
            label = f"{rt.hotel.name} — {rt.name} ({meal_plan.value})" if rt else "Hotel"
            breakdown.append({
                "type": "hotel",
                "description": label,
                "detail": f"₹{rate:,.0f} × {nights} nights",
                "amount": float(line_total),
            })

        # ── Vehicle cost ──────────────────────────────────────────────────────
        vehicle_cost = Decimal("0")
        if vehicle_id:
            vehicle_cost = await self.get_vehicle_rate(db, vehicle_id, num_days, travel_date)
            v_result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
            v = v_result.scalar_one_or_none()
            v_label = v.vehicle_type if v else "Vehicle"
            breakdown.append({
                "type": "vehicle",
                "description": f"{v_label} ({num_days} days)",
                "detail": f"₹{vehicle_cost / num_days:,.0f}/day × {num_days}",
                "amount": float(vehicle_cost),
            })

        # ── Activity cost ─────────────────────────────────────────────────────
        activity_cost = await self.get_activity_total(db, activity_ids, num_adults, num_children)
        if activity_cost > 0:
            breakdown.append({
                "type": "activities",
                "description": f"Optional Activities ({len(activity_ids)})",
                "detail": "Per person pricing",
                "amount": float(activity_cost),
            })

        # ── Totals ────────────────────────────────────────────────────────────
        base_cost = _round(hotel_cost + vehicle_cost + activity_cost)
        markup_amount = await self.apply_agent_markup(db, base_cost, agent_user)
        subtotal = _round(base_cost + markup_amount)
        gst_amount = self.calculate_gst(subtotal)
        total_cost = _round(subtotal + gst_amount)

        season = _detect_season(travel_date)

        return {
            "hotel_cost": float(hotel_cost),
            "vehicle_cost": float(vehicle_cost),
            "activity_cost": float(activity_cost),
            "base_cost": float(base_cost),
            "markup_amount": float(markup_amount),
            "gst_amount": float(gst_amount),
            "total_cost": float(total_cost),
            "gst_rate": float(settings.DEFAULT_GST_RATE),
            "breakdown": breakdown,
            "season_applied": season.value if season else None,
        }


# Singleton
pricing_engine = PricingEngine()