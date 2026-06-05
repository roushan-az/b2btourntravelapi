"""Destinations Router — CRUD + image upload."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import Destination, Hotel, User
from app.schemas import (
    DestinationCreate, DestinationResponse, DestinationUpdate,
    MessageResponse, PaginatedResponse,
)
from app.services.auth_service import get_current_admin, get_current_user
from app.services.blob_service import blob_service

router = APIRouter(prefix="/destinations", tags=["Destinations"])


async def _to_response(dest: Destination, db: AsyncSession) -> DestinationResponse:
    count_result = await db.execute(
        select(func.count()).where(Hotel.destination_id == dest.id, Hotel.is_active == True)
    )
    hotel_count = count_result.scalar_one()
    data = DestinationResponse.model_validate(dest)
    data.hotel_count = hotel_count
    return data


# ── Public / Agent endpoints ─────────────────────────────────────────────────

@router.get("", response_model=list[DestinationResponse])
async def list_destinations(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return all active destinations ordered by sort_order."""
    q = select(Destination).order_by(Destination.sort_order, Destination.name)
    if active_only:
        q = q.where(Destination.is_active == True)
    result = await db.execute(q)
    dests = result.scalars().all()
    return [await _to_response(d, db) for d in dests]


@router.get("/{destination_id}", response_model=DestinationResponse)
async def get_destination(
    destination_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Destination).where(Destination.id == destination_id))
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")
    return await _to_response(dest, db)


@router.get("/slug/{slug}", response_model=DestinationResponse)
async def get_destination_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Destination).where(Destination.slug == slug))
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")
    return await _to_response(dest, db)


# ── Admin endpoints ──────────────────────────────────────────────────────────

@router.post("", response_model=DestinationResponse, status_code=status.HTTP_201_CREATED)
async def create_destination(
    payload: DestinationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    # Ensure slug uniqueness
    existing = await db.execute(select(Destination).where(Destination.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{payload.slug}' already exists")

    dest = Destination(**payload.model_dump())
    db.add(dest)
    await db.flush()
    await db.refresh(dest)
    return await _to_response(dest, db)


@router.patch("/{destination_id}", response_model=DestinationResponse)
async def update_destination(
    destination_id: UUID,
    payload: DestinationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(Destination).where(Destination.id == destination_id))
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dest, field, value)
    db.add(dest)
    await db.flush()
    await db.refresh(dest)
    return await _to_response(dest, db)


@router.delete("/{destination_id}", response_model=MessageResponse)
async def delete_destination(
    destination_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(Destination).where(Destination.id == destination_id))
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")

    # Check for linked hotels
    hotel_check = await db.execute(select(func.count()).where(Hotel.destination_id == destination_id))
    if hotel_check.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete destination with linked hotels. Remove hotels first.",
        )
    await db.delete(dest)
    return MessageResponse(message=f"Destination '{dest.name}' deleted")


@router.post("/{destination_id}/image", response_model=DestinationResponse)
async def upload_destination_image(
    destination_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(Destination).where(Destination.id == destination_id))
    dest = result.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")

    # Delete old image if exists
    if dest.image_blob_name:
        blob_service.delete_blob(settings.AZURE_CONTAINER_DESTINATIONS, dest.image_blob_name)

    blob_name, public_url = await blob_service.upload_image(
        file=file,
        container_name=settings.AZURE_CONTAINER_DESTINATIONS,
        prefix=dest.slug,
    )
    dest.image_blob_name = blob_name
    dest.image_url = public_url
    db.add(dest)
    await db.flush()
    await db.refresh(dest)
    return await _to_response(dest, db)