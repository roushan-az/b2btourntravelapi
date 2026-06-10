"""
Authentication Service — JWT tokens, password hashing, current user dependency.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
import random
import string

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app.config import settings
from app.database import get_db
from app.models import Agent, User, UserRole, PasswordResetOTP
from app.schemas import RegisterRequest
from app.services.email_service import send_otp_email

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

def create_reset_token(email: str) -> str:
    return _create_token(
        {"sub": email, "type": "reset"},
        timedelta(minutes=15),
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user

async def get_current_agent(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.AGENT, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent access required")
    if user.role == UserRole.AGENT:
        if not user.agent_profile or not user.agent_profile.is_approved:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent account pending approval")
    return user

# ── Authenticate user (login) ─────────────────────────────────────────────────
async def authenticate_user(email: str, password: str, db: AsyncSession) -> Optional[User]:
    result = await db.execute(
        select(User)
        .options(selectinload(User.agent_profile))
        .where(User.email == email.lower().strip())
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

async def register_new_agent(payload: RegisterRequest, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.email == payload.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already registered.")

    new_user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.AGENT,
        is_active=False,
        is_verified=False
    )
    db.add(new_user)
    await db.flush()

    new_agent_profile = Agent(
        user_id=new_user.id,
        agency_name=payload.agency_name,
        is_approved=False
    )
    db.add(new_agent_profile)
    await db.commit()
    await db.refresh(new_user)
    return new_user

def generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))

# ── 1. Request OTP ────────────────────────────────────────────────────────
async def handle_forgot_password(email: str, db: AsyncSession):
    email = email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return True # Return true anyway to prevent email enumeration attacks

    otp_plain = generate_otp()
    otp_hashed = hash_password(otp_plain)
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)

    new_otp = PasswordResetOTP(
        user_id=user.id,
        email=email,
        otp_code=otp_plain,
        otp_hash=otp_hashed,
        expires_at=expires
    )
    db.add(new_otp)
    await db.commit()

    await send_otp_email(email, otp_plain)
    return True

# ── 2. Verify OTP ─────────────────────────────────────────────────────────
async def verify_reset_otp(email: str, otp: str, db: AsyncSession) -> str:
    email = email.lower().strip()
    result = await db.execute(
        select(PasswordResetOTP)
        .where(PasswordResetOTP.email == email)
        .where(PasswordResetOTP.is_used == False)
        .order_by(PasswordResetOTP.id.desc())
    )
    otp_record = result.scalars().first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    # Convert naive datetime to aware for accurate comparison
    current_time = datetime.now(timezone.utc)
    if otp_record.expires_at.tzinfo is None:
        otp_record.expires_at = otp_record.expires_at.replace(tzinfo=timezone.utc)

    if current_time > otp_record.expires_at:
        raise HTTPException(status_code=400, detail="OTP has expired.")

    if otp_record.otp_code != otp:
        otp_record.attempts += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Incorrect OTP.")

    otp_record.is_used = True
    await db.commit()
    return create_reset_token(email)

# ── 3. Execute Password Reset ─────────────────────────────────────────────
async def execute_password_reset(reset_token: str, new_password: str, db: AsyncSession):
    payload = decode_token(reset_token)
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Invalid token type.")

    email = payload.get("sub")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.hashed_password = hash_password(new_password)
    await db.commit()
    return True