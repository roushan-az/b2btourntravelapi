"""Pricing Rules Router — Admin manages seasonal multipliers and GST config."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Season, SeasonalPricingRule, User
from app.schemas import MessageResponse, SeasonalPricingRuleSchema
from app.services.auth_service import get_current_admin

router = APIRouter(prefix="/pricing", tags=["Pricing Rules"])


@router.get("/seasonal", response_model=list[SeasonalPricingRuleSchema])
async def list_seasonal_rules(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    result = await db.execute(select(SeasonalPricingRule).order_by(SeasonalPricingRule.season))
    return result.scalars().all()


@router.put("/seasonal", response_model=list[SeasonalPricingRuleSchema])
async def upsert_seasonal_rules(
    rules: list[SeasonalPricingRuleSchema],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """Replace all seasonal pricing rules in bulk."""
    existing = await db.execute(select(SeasonalPricingRule))
    for r in existing.scalars().all():
        await db.delete(r)
    new_rules = []
    for rule in rules:
        obj = SeasonalPricingRule(**rule.model_dump())
        db.add(obj)
        new_rules.append(obj)
    await db.flush()
    await db.commit()
    return new_rules


@router.patch("/seasonal/{season}", response_model=SeasonalPricingRuleSchema)
async def update_seasonal_rule(
    season: Season,
    rule: SeasonalPricingRuleSchema,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(SeasonalPricingRule).where(SeasonalPricingRule.season == season))
    obj = result.scalar_one_or_none()
    if not obj:
        obj = SeasonalPricingRule(season=season)
    for field, value in rule.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.add(obj)
    await db.flush()
    await db.commit()
    await db.refresh(obj)
    return obj