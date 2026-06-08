"""
Authentication Service — JWT tokens, password hashing, current user dependency.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app.config import settings
from app.database import get_db
from app.models import Agent, User, UserRole
from app.schemas import RegisterRequest
import random
import string
from app.models import User


# This is a simple memory-based cache for OTPs.
# In production, use Redis.
otp_cache = {}

# ── Password hashing ──────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Token helpers ─────────────────────────────────────────────────────────────
def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: UUID, role: UserRole) -> str:
    return _create_token(
        {"sub": str(user_id), "role": role.value, "type": "access"},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: UUID) -> str:
    return _create_token(
        {"sub": str(user_id), "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── FastAPI dependencies ──────────────────────────────────────────────────────
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(
        select(User)
        .options(selectinload(User.agent_profile))
        .where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def get_current_agent(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.AGENT, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent access required",
        )
    if user.role == UserRole.AGENT:
        if not user.agent_profile or not user.agent_profile.is_approved:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Agent account pending approval",
            )
    return user


# ── Authenticate user (login) ─────────────────────────────────────────────────
async def authenticate_user(email: str, password: str, db: AsyncSession) -> Optional[User]:
    result = await db.execute(
        select(User)
        .options(selectinload(User.agent_profile))
        .where(User.email == email.lower().strip())
    )
    user = result.scalar_one_or_none()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# Assuming you already have 'hash_password' defined in this file

async def register_new_agent(payload: RegisterRequest, db: AsyncSession) -> User:
    """Handles the complete registration flow for a new agent."""

    # 1. Check if the email is already in use
    result = await db.execute(select(User).where(User.email == payload.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered."
        )

    # 2. Hash the password
    hashed_pw = hash_password(payload.password)

    # 3. Create the Base User (Inactive by default)
    new_user = User(
        email=payload.email,
        hashed_password=hashed_pw,
        full_name=payload.full_name,
        role=UserRole.AGENT,
        is_active=False,
        is_verified=False
    )

    db.add(new_user)
    await db.flush()  # Assigns an ID to new_user before creating Agent profile

    # 4. Create the linked Agent Profile
    new_agent_profile = Agent(
        user_id=new_user.id,
        agency_name=payload.agency_name,
        is_approved=False
    )

    db.add(new_agent_profile)

    # 5. Commit both records
    await db.commit()
    await db.refresh(new_user)

    return new_user


def generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))


async def send_otp_to_email(email: str, db: AsyncSession):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        otp = generate_otp()  # Ensure this helper exists
        otp_cache[email] = otp
        # Add your actual SMTP logic here
        print(f"DEBUG: Sending OTP {otp} to {email}")
    return True


async def verify_otp_and_reset(email: str, otp: str, new_password: str, db: AsyncSession):
    stored_otp = otp_cache.get(email)
    if not stored_otp or stored_otp != otp:
        return False

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        user.hashed_password = hash_password(new_password)
        await db.commit()
        del otp_cache[email]
        return True
    return False