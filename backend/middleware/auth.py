from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.database.models import User
from backend.utils.security import decode_access_token

# tokenUrl is only used to power the "Authorize" button in the /docs UI;
# the actual login endpoint accepts a JSON body, not an OAuth2 form.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# Same, but doesn't raise on a missing/malformed header - for routes that
# work for anyone but behave differently if the caller happens to be logged in.
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: reads the JWT from the Authorization header,
    validates it, and loads the matching User from the database.
    Use as `current_user: User = Depends(get_current_user)` on any route
    that should require a logged-in user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency: same as get_current_user, but additionally requires
    the user's role to be "admin". Use on any route that only admins should
    reach (e.g. course approval/rejection)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def get_current_paying_user(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency: requires is_premium=True (i.e. an active Stripe
    subscription, see routes/billingRoute.py) or role "admin". Any user of
    any role can submit a course once they've paid - this is intentionally
    not tied to `role`."""
    if not current_user.is_premium and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A premium subscription is required to submit a course")
    return current_user


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Same as get_current_user, but returns None instead of raising when
    there's no token or it's invalid. Used on routes that are mostly public
    but need to know "is this the course's own submitter/an admin" to decide
    whether to reveal a pending/rejected course."""
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    user_id = payload.get("user_id")
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()
