"""Common API dependencies: database sessions, authentication, and role authorization."""

from typing import Generator, Sequence
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.user import User
from app.models.enums import UserRole

# OAuth2 Bearer scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Retrieve and validate the currently authenticated user from the JWT token.

    Raises:
        HTTPException(401): If token is missing, expired, invalid, or user does not exist.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = int(user_id_raw)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


class RoleChecker:
    """Reusable dependency to restrict endpoint access by UserRole."""

    def __init__(self, *allowed_roles: UserRole):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return current_user


# Role-based dependency shortcuts
require_admin = RoleChecker(UserRole.ADMIN)
require_agent = RoleChecker(UserRole.AGENT)
require_agent_or_admin = RoleChecker(UserRole.AGENT, UserRole.ADMIN)
require_customer = RoleChecker(UserRole.CUSTOMER)
require_authenticated = get_current_user

__all__ = [
    "get_db",
    "oauth2_scheme",
    "get_current_user",
    "RoleChecker",
    "require_admin",
    "require_agent",
    "require_agent_or_admin",
    "require_customer",
    "require_authenticated",
]
