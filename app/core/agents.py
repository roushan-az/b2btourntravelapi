from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, User
from app.schemas import MessageResponse
from app.services.auth_service import get_current_admin

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
async def list_agents(
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin)
):
    """Fetch all registered agents for the admin dashboard."""
    # Use an explicit JOIN instead of relying on a relationship attribute
    result = await db.execute(
        select(Agent, User).join(User, Agent.user_id == User.id)
    )
    rows = result.all()

    response = []
    for agent, user in rows:
        response.append({
            "id": agent.id,
            "agency_name": agent.agency_name,
            "city": getattr(agent, 'city', "N/A"),
            "is_approved": agent.is_approved,
            "email": user.email,
            "full_name": user.full_name
        })

    return {"items": response}


@router.post("/{agent_id}/approve", response_model=MessageResponse)
async def approve_agent(
        agent_id: UUID,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin)
):
    """Approves the agent and activates their user account."""
    # 1. Fetch Agent
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 2. Fetch linked User
    user_result = await db.execute(select(User).where(User.id == agent.user_id))
    user = user_result.scalar_one_or_none()

    # 3. Update both
    agent.is_approved = True
    if user:
        user.is_active = True  # Allows them to log in

    await db.commit()
    return MessageResponse(message=f"Agent '{agent.agency_name}' approved successfully")


@router.post("/{agent_id}/suspend", response_model=MessageResponse)
async def suspend_agent(
        agent_id: UUID,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_admin)
):
    """Suspends the agent and deactivates their user account."""
    # 1. Fetch Agent
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 2. Fetch linked User
    user_result = await db.execute(select(User).where(User.id == agent.user_id))
    user = user_result.scalar_one_or_none()

    # 3. Update both
    agent.is_approved = False
    if user:
        user.is_active = False  # Blocks them from logging in

    await db.commit()
    return MessageResponse(message=f"Agent '{agent.agency_name}' suspended")