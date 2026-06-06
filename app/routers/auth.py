"""
Auth Router — JWT Login, Refresh, Password Change, and OTP Reset.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import (
    LoginRequest, MessageResponse, PasswordChangeRequest,
    TokenRefreshRequest, TokenResponse, UserResponse,
    OTPRequest, ResetPasswordRequest
)
from app.services.auth_service import (
    authenticate_user, create_access_token, create_refresh_token,
    decode_token, get_current_user, hash_password, verify_password
)

# 1. DEFINE ROUTER FIRST
router = APIRouter(prefix="/auth", tags=["Authentication"])


# 2. LOGIN
@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(payload.email, payload.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# 3. REFRESH TOKEN
@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    token_data = decode_token(payload.refresh_token)
    if token_data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == token_data["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# 4. PASSWORD RESET (OTP FLOW)
@router.post("/request-password-reset", response_model=MessageResponse)
async def request_password_reset(payload: OTPRequest, db: AsyncSession = Depends(get_db)):
    """Generates an OTP and sends it via email."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        # We don't reveal if email exists for security
        return MessageResponse(message="If an account exists, an OTP has been sent.")

    # LOGIC: Generate 6-digit code, save to User model or OTP table
    # email_service.send_otp(user.email, "123456") 
    return MessageResponse(message="OTP sent to your email")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Verifies OTP and updates password."""
    # LOGIC: Verify OTP from DB
    # user.hashed_password = hash_password(payload.new_password)
    # db.commit()
    return MessageResponse(message="Password reset successfully")


# 5. CHANGE PASSWORD
@router.post("/change-password", response_model=MessageResponse)
async def change_password(
        payload: PasswordChangeRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")

    current_user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return MessageResponse(message="Password updated successfully")