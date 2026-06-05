"""Hotels Router — Full CRUD, room type & rate management, image upload."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import Destination, Hotel, MealPlanRate, RoomType, User
from app.schemas import (
    HotelCreate, HotelResponse, HotelUpdate,
    MealPlanRateSchema, MessageResponse, RoomTypeCreate, RoomTypeResponse,
)
from app.services.auth_service import get_current_admin, get_current_user
from app.services.blob_service import blob_service

router = APIRouter(prefix="/hotels", tags=["Hotels"])


async def _load_hotel(hotel_id: UUID, db: AsyncSession) -> Hotel:
    result = await db.execute(
        select(Hotel)
        .options(
            selectinload(Hotel.destination_rel),
            selectinload(Hotel.room_types).selectinload(RoomType.meal_plan_rates),
            selectinload(Hotel.room_types).selectinload(RoomType.seasonal_rates),
        )
        .where(Hotel.id == hotel_id)
    )
    hotel = result.scalar_one_or_none()
    if not hotel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotel not found")
    return hotel


def _hotel_to_response(hotel: Hotel) -> HotelResponse:
    data = HotelResponse.model_validate(hotel)
    if hotel.destination_rel:
        data.destination_name = hotel.destination_rel.name
        data.destination_slug = hotel.destination_rel.slug
    return data


# ── Agent endpoints ───────────────────────────────────────────────────────────

@router.get("", response_model=list[HotelResponse])
async def list_hotels(
    destination_id: Optional[UUID] = Query(None),
    destination_slug: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = (
        select(Hotel)
        .options(
            selectinload(Hotel.destination_rel),
            selectinload(Hotel.room_types).selectinload(RoomType.meal_plan_rates),
            selectinload(Hotel.room_types).selectinload(RoomType.seasonal_rates),
        )
        .order_by(Hotel.sort_order, Hotel.name)
    )
    if active_only:
        q = q.where(Hotel.is_active == True)
    if destination_id:
        q = q.where(Hotel.destination_id == destination_id)
    elif destination_slug:
        dest_result = await db.execute(select(Destination).where(Destination.slug == destination_slug))
        dest = dest_result.scalar_one_or_none()
        if dest:
            q = q.where(Hotel.destination_id == dest.id)
        else:
            return []

    result = await db.execute(q)
    return [_hotel_to_response(h) for h in result.scalars().all()]


@router.get("/{hotel_id}", response_model=HotelResponse)
async def get_hotel(
    hotel_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _hotel_to_response(await _load_hotel(hotel_id, db))


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.post("", response_model=HotelResponse, status_code=status.HTTP_201_CREATED)
async def create_hotel(
    payload: HotelCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    # Validate destination
    dest_result = await db.execute(select(Destination).where(Destination.id == payload.destination_id))
    if not dest_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")

    hotel_data = payload.model_dump(exclude={"room_types", "image_url"})
    hotel = Hotel(**hotel_data)
    if payload.image_url:
        hotel.image_url = payload.image_url
    db.add(hotel)
    await db.flush()

    # Create room types + rates
    for rt_data in payload.room_types:
        rates_data = rt_data.meal_plan_rates
        rt = RoomType(**rt_data.model_dump(exclude={"meal_plan_rates"}), hotel_id=hotel.id)
        db.add(rt)
        await db.flush()
        for rate in rates_data:
            db.add(MealPlanRate(**rate.model_dump(), room_type_id=rt.id))

    await db.flush()
    return _hotel_to_response(await _load_hotel(hotel.id, db))


@router.patch("/{hotel_id}", response_model=HotelResponse)
async def update_hotel(
    hotel_id: UUID,
    payload: HotelUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    hotel = await _load_hotel(hotel_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(hotel, field, value)
    db.add(hotel)
    await db.flush()
    return _hotel_to_response(await _load_hotel(hotel_id, db))


@router.delete("/{hotel_id}", response_model=MessageResponse)
async def delete_hotel(
    hotel_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    hotel = await _load_hotel(hotel_id, db)
    if hotel.image_blob_name:
        blob_service.delete_blob(settings.AZURE_CONTAINER_HOTELS, hotel.image_blob_name)
    await db.delete(hotel)
    return MessageResponse(message=f"Hotel '{hotel.name}' deleted")


@router.post("/{hotel_id}/image", response_model=HotelResponse)
async def upload_hotel_image(
    hotel_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    hotel = await _load_hotel(hotel_id, db)
    if hotel.image_blob_name:
        blob_service.delete_blob(settings.AZURE_CONTAINER_HOTELS, hotel.image_blob_name)

    blob_name, public_url = await blob_service.upload_image(
        file=file,
        container_name=settings.AZURE_CONTAINER_HOTELS,
        prefix=hotel.id.hex[:8],
    )
    hotel.image_blob_name = blob_name
    hotel.image_url = public_url
    db.add(hotel)
    await db.flush()
    return _hotel_to_response(await _load_hotel(hotel_id, db))


# ── Room Types sub-resource ───────────────────────────────────────────────────

@router.post("/{hotel_id}/room-types", response_model=RoomTypeResponse, status_code=status.HTTP_201_CREATED)
async def add_room_type(
    hotel_id: UUID,
    payload: RoomTypeCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    hotel = await _load_hotel(hotel_id, db)
    rt = RoomType(**payload.model_dump(exclude={"meal_plan_rates"}), hotel_id=hotel.id)
    db.add(rt)
    await db.flush()
    for rate in payload.meal_plan_rates:
        db.add(MealPlanRate(**rate.model_dump(), room_type_id=rt.id))
    await db.flush()
    await db.refresh(rt)
    return rt


@router.patch("/{hotel_id}/room-types/{room_type_id}/rates", response_model=MessageResponse)
async def update_meal_plan_rates(
    hotel_id: UUID,
    room_type_id: UUID,
    rates: list[MealPlanRateSchema],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """Replace all meal plan rates for a room type."""
    result = await db.execute(select(RoomType).where(RoomType.id == room_type_id, RoomType.hotel_id == hotel_id))
    rt = result.scalar_one_or_none()
    if not rt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room type not found")

    # Delete existing rates
    existing = await db.execute(select(MealPlanRate).where(MealPlanRate.room_type_id == room_type_id))
    for r in existing.scalars().all():
        await db.delete(r)

    # Insert new
    for rate in rates:
        db.add(MealPlanRate(**rate.model_dump(), room_type_id=room_type_id))

    return MessageResponse(message="Meal plan rates updated")


@router.delete("/{hotel_id}/room-types/{room_type_id}", response_model=MessageResponse)
async def delete_room_type(
    hotel_id: UUID,
    room_type_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(RoomType).where(RoomType.id == room_type_id, RoomType.hotel_id == hotel_id))
    rt = result.scalar_one_or_none()
    if not rt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room type not found")
    await db.delete(rt)
    return MessageResponse(message=f"Room type '{rt.name}' deleted")