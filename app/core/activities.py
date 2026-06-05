"""Activities Router — CRUD for sightseeing and adventure activities."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Activity, Destination, User
from app.schemas import ActivityCreate, ActivityResponse, ActivityUpdate, MessageResponse
from app.services.auth_service import get_current_admin, get_current_user
from app.services.blob_service import blob_service

router = APIRouter(prefix="/activities", tags=["Activities"])


def _to_response(act: Activity, dest_name: Optional[str] = None) -> ActivityResponse:
    data = ActivityResponse.model_validate(act)
    data.destination_name = dest_name
    return data


@router.get("", response_model=list[ActivityResponse])
async def list_activities(
    destination_id: Optional[UUID] = Query(None),
    category: Optional[str] = Query(None),
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Activity).order_by(Activity.sort_order, Activity.name)
    if active_only:
        q = q.where(Activity.is_active == True)
    if destination_id:
        q = q.where(Activity.destination_id == destination_id)
    if category:
        q = q.where(Activity.category == category)
    result = await db.execute(q)
    acts = result.scalars().all()

    responses = []
    for act in acts:
        dest_name = None
        if act.destination_id:
            d_result = await db.execute(select(Destination).where(Destination.id == act.destination_id))
            d = d_result.scalar_one_or_none()
            if d:
                dest_name = d.name
        responses.append(_to_response(act, dest_name))
    return responses


@router.get("/{activity_id}", response_model=ActivityResponse)
async def get_activity(activity_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    return _to_response(act)


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(payload: ActivityCreate, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    act = Activity(**payload.model_dump(exclude={"image_url"}))
    if payload.image_url:
        act.image_url = payload.image_url
    db.add(act)
    await db.flush()
    await db.refresh(act)
    return _to_response(act)


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def update_activity(activity_id: UUID, payload: ActivityUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(act, field, value)
    db.add(act)
    await db.flush()
    await db.refresh(act)
    return _to_response(act)


@router.delete("/{activity_id}", response_model=MessageResponse)
async def delete_activity(activity_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    await db.delete(act)
    return MessageResponse(message=f"Activity '{act.name}' deleted")