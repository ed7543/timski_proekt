import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.database.models import User, VerificationToken
from backend.middleware.auth import get_current_user
from backend.middleware.rate_limit import limiter
from backend.utils.time import utcnow
from backend.models.authRequest import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from backend.utils.email import send_verification_email, send_password_reset_email
from backend.utils.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

VERIFICATION_TOKEN_EXPIRE_HOURS = 24
RESET_TOKEN_EXPIRE_HOURS = 1


def _create_token(db: Session, user: User, purpose: str, expire_hours: int) -> str:
    """Create and persist a single-use token tied to a user (email verification / password reset)."""
    token = secrets.token_urlsafe(32)
    record = VerificationToken(
        user_id=user.id,
        token=token,
        purpose=purpose,
        expires_at=utcnow() + timedelta(hours=expire_hours),
    )
    db.add(record)
    db.commit()
    return token


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account and return a JWT access token."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    verify_token = _create_token(db, user, "verify_email", VERIFICATION_TOKEN_EXPIRE_HOURS)
    send_verification_email(user.email, verify_token)

    token = create_access_token({"sub": user.email, "user_id": user.id})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    """Verify credentials and return a JWT access token."""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token({"sub": user.email, "user_id": user.id})
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout():
    """Stateless JWT - there's nothing to invalidate server-side; the client just discards the token."""
    return {"message": "Logged out"}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    """Return info about the currently logged-in user. Requires a valid Bearer token."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_verified": current_user.is_verified,
    }


@router.get("/verify-email")
async def verify_email(token: str, db: Session = Depends(get_db)):
    """Confirm a user's email using the token sent (logged) at registration time."""
    record = (
        db.query(VerificationToken)
        .filter(VerificationToken.token == token, VerificationToken.purpose == "verify_email")
        .first()
    )
    if not record or record.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == record.user_id).first()
    user.is_verified = True
    db.delete(record)
    db.commit()
    return {"message": "Email verified successfully"}


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Request a password reset link. Always returns the same message so we don't leak
    which emails are registered."""
    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        reset_token = _create_token(db, user, "reset_password", RESET_TOKEN_EXPIRE_HOURS)
        send_password_reset_email(user.email, reset_token)
    return {"message": "If that email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Set a new password using a token obtained from /forgot-password."""
    record = (
        db.query(VerificationToken)
        .filter(VerificationToken.token == payload.token, VerificationToken.purpose == "reset_password")
        .first()
    )
    if not record or record.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == record.user_id).first()
    user.hashed_password = hash_password(payload.new_password)
    db.delete(record)
    db.commit()
    return {"message": "Password reset successfully"}
