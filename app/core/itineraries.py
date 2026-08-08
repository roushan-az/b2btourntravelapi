"""Itinerary Blocks Router — CRUD, smart-route query, image upload."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ItineraryBlock, User
from app.schemas import (
    ItineraryBlockCreate, ItineraryBlockResponse, ItineraryBlockUpdate, MessageResponse,
)
from app.services.auth_service import get_current_admin, get_current_user
from app.services.blob_service import blob_service

router = APIRouter(prefix="/itineraries", tags=["Itinerary Blocks"])


# ── Agent endpoints ───────────────────────────────────────────────────────────

@router.get("", response_model=list[ItineraryBlockResponse])
async def list_itinerary_blocks(
    day_number: Optional[int] = Query(None, ge=1, le=14, description="Filter by day number"),
    departs_from: Optional[str] = Query(None, description="Filter by departure point (slug or 'arrival')"),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Smart-route query: pass day_number + departs_from to get only
    the itinerary options valid for that step in the package builder.
    """
    q = select(ItineraryBlock).order_by(ItineraryBlock.day_number, ItineraryBlock.sort_order)
    if active_only:
        q = q.where(ItineraryBlock.is_active == True)
    if day_number is not None:
        q = q.where(ItineraryBlock.day_number == day_number)
    if departs_from is not None:
        q = q.where(ItineraryBlock.departs_from == departs_from.lower())

    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{block_id}", response_model=ItineraryBlockResponse)
async def get_itinerary_block(
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(ItineraryBlock).where(ItineraryBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary block not found")
    return block


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.post("", response_model=ItineraryBlockResponse, status_code=status.HTTP_201_CREATED)
async def create_itinerary_block(
    payload: ItineraryBlockCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    # Validate overnight_destination_id if given
    if payload.overnight_destination_id:
        from app.models import Destination
        dest_result = await db.execute(
            select(Destination).where(Destination.id == payload.overnight_destination_id)
        )
        dest = dest_result.scalar_one_or_none()
        if not dest:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overnight destination not found")
        # Auto-fill slug
        data = payload.model_dump()
        data["overnight_slug"] = dest.slug
    else:
        data = payload.model_dump()

    block = ItineraryBlock(**data)
    db.add(block)
    await db.flush()
    await db.commit()
    await db.refresh(block)
    return block


@router.patch("/{block_id}", response_model=ItineraryBlockResponse)
async def update_itinerary_block(
    block_id: UUID,
    payload: ItineraryBlockUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(ItineraryBlock).where(ItineraryBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary block not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(block, field, value)
    db.add(block)
    await db.flush()
    await db.commit()
    await db.refresh(block)
    return block


@router.delete("/{block_id}", response_model=MessageResponse)
async def delete_itinerary_block(
        block_id: UUID,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin),
):
    result = await db.execute(select(ItineraryBlock).where(ItineraryBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary block not found")

    await db.delete(block)
    await db.commit()  # <--- ADD THIS EXACT LINE

    return MessageResponse(message=f"Itinerary block '{block.title[:40]}' deleted")


@router.post("/{block_id}/image", response_model=ItineraryBlockResponse)
async def upload_block_image(
    block_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(ItineraryBlock).where(ItineraryBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary block not found")

    if block.image_blob_name:
        blob_service.delete_blob(settings.AZURE_CONTAINER_ITINERARIES, block.image_blob_name)

    blob_name, public_url = await blob_service.upload_image(
        file=file,
        container_name=settings.AZURE_CONTAINER_ITINERARIES,
        prefix=f"day{block.day_number}",
    )
    block.image_blob_name = blob_name
    block.image_url = public_url
    db.add(block)
    await db.flush()
    await db.commit()
    await db.refresh(block)
    return block