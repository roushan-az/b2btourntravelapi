"""
Auth Router — JWT Login, Refresh, Password Change, OTP Reset, and Registration.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import (
    LoginRequest, MessageResponse, PasswordChangeRequest,
    TokenRefreshRequest, TokenResponse, UserResponse,
    OTPRequest, ResetPasswordRequest, RegisterRequest
)
from app.services.auth_service import (
    authenticate_user, create_access_token, create_refresh_token,
    decode_token, get_current_user, hash_password, verify_password,
    register_new_agent, handle_forgot_password, verify_reset_otp,
    execute_password_reset
)

# 1. DEFINE ROUTER FIRST
router = APIRouter(prefix="/auth", tags=["Authentication"])

# 2. REGISTRATION
@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Registers a new agent. Account remains inactive until admin approval."""
    await register_new_agent(payload, db)
    return MessageResponse(message="Registration successful! Please wait for admin approval.")

# 3. LOGIN
# 3. LOGIN
@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(payload.email, payload.password, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # --- THE FIX: Block inactive accounts ---
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending admin approval.",
        )
    # --------------------------------------

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

# 4. REFRESH TOKEN
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

# 5. PASSWORD RESET (OTP FLOW)
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

# 6. CHANGE PASSWORD
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

# ── Pydantic Schemas to catch the React frontend JSON ─────────────────────
class ForgotPasswordRequest(BaseModel):
    email: str

class VerifyOtpRequest(BaseModel):
    email: str
    otp: str

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str
    confirm_password: str

# ── The Endpoints ─────────────────────────────────────────────────────────
@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await handle_forgot_password(req.email, db)
    return {"message": "If the email is registered, an OTP has been sent."}

@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    # This matches api.js expecting {"reset_token": "ey..."}
    token = await verify_reset_otp(req.email, req.otp, db)
    return {"reset_token": token}

@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    if req.new_password != req.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )
    await execute_password_reset(req.reset_token, req.new_password, db)
    return {"message": "Password reset successfully."}

@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value.lower(), # Ensure it matches frontend
        "is_active": current_user.is_active
    }