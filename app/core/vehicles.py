"""Vehicles Router — CRUD + seasonal rates + image upload."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import User, Vehicle, VehicleSeasonalRate
from app.schemas import MessageResponse, VehicleCreate, VehicleResponse, VehicleUpdate, VehicleSeasonalRateSchema
from app.services.auth_service import get_current_admin, get_current_user
from app.services.blob_service import blob_service

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


async def _load_vehicle(vehicle_id: UUID, db: AsyncSession) -> Vehicle:
    result = await db.execute(
        select(Vehicle)
        .options(selectinload(Vehicle.seasonal_rates))
        .where(Vehicle.id == vehicle_id)
    )
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return v


@router.get("", response_model=list[VehicleResponse])
async def list_vehicles(
        active_only: bool = True,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_user),
):
    q = select(Vehicle).options(selectinload(Vehicle.seasonal_rates)).order_by(Vehicle.sort_order, Vehicle.capacity_pax)
    if active_only:
        q = q.where(Vehicle.is_active == True)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(vehicle_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await _load_vehicle(vehicle_id, db)


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
        payload: VehicleCreate,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin)
):
    # Safely dump payload to dict, excluding unset fields
    vehicle_data = payload.model_dump(exclude_unset=True)
    vehicle = Vehicle(**vehicle_data)

    db.add(vehicle)
    await db.flush()
    await db.commit()
    return await _load_vehicle(vehicle.id, db)


@router.patch("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
        vehicle_id: UUID,
        payload: VehicleUpdate,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin)
):
    vehicle = await _load_vehicle(vehicle_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(vehicle, field, value)
    db.add(vehicle)
    await db.flush()
    await db.commit()
    return await _load_vehicle(vehicle_id, db)


@router.patch("/{vehicle_id}/seasonal-rates", response_model=MessageResponse)
async def update_seasonal_rates(
        vehicle_id: UUID,
        rates: list[VehicleSeasonalRateSchema],
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin),
):
    vehicle = await _load_vehicle(vehicle_id, db)
    existing = await db.execute(select(VehicleSeasonalRate).where(VehicleSeasonalRate.vehicle_id == vehicle_id))
    for r in existing.scalars().all():
        await db.delete(r)
    for rate in rates:
        db.add(VehicleSeasonalRate(**rate.model_dump(), vehicle_id=vehicle_id))

    await db.commit()  # Ensure the new rates commit safely
    return MessageResponse(message="Seasonal rates updated")


@router.delete("/{vehicle_id}", response_model=MessageResponse)
async def delete_vehicle(
        vehicle_id: UUID,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin)
):
    # 1. Fetch vehicle directly to bypass heavy relationship conflicts
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    # 2. Explicitly query and delete child seasonal rates to satisfy foreign key constraints
    vsr_result = await db.execute(select(VehicleSeasonalRate).where(VehicleSeasonalRate.vehicle_id == vehicle_id))
    for rate in vsr_result.scalars().all():
        await db.delete(rate)

    # 3. Delete the vehicle record
    await db.delete(vehicle)

    # 4. Force a hard commit
    await db.commit()

    return MessageResponse(message=f"Vehicle '{vehicle.vehicle_type}' deleted")


@router.post("/{vehicle_id}/image", response_model=VehicleResponse)
async def upload_vehicle_image(
        vehicle_id: UUID,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin),
):
    vehicle = await _load_vehicle(vehicle_id, db)
    blob_name, public_url = await blob_service.upload_image(file, settings.AZURE_CONTAINER_VEHICLES, prefix="vehicles")
    vehicle.image_url = public_url
    db.add(vehicle)
    await db.flush()
    await db.commit()
    return await _load_vehicle(vehicle_id, db)