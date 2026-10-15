"""Authentication and user session management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.api.deps import (
    get_db,
    get_current_user,
    require_admin,
    require_agent_or_admin,
)
from app.models.user import User
from app.schemas.user import (
    CustomerRegisterRequest,
    UserLoginRequest,
    UserRead,
    TokenResponse,
)
from app.services.user import user_service

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register Customer",
    description=(
        "Register a new customer account. Public self-registration always assigns "
        "the customer role; role escalation attempts are strictly prevented."
    ),
)
def register_customer(
    request: CustomerRegisterRequest,
    db: Session = Depends(get_db),
) -> UserRead:
    """Register a new customer account."""
    existing_user = user_service.get_by_email(db, email=request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered.",
        )

    user = user_service.create_customer(
        db,
        name=request.name,
        email=request.email,
        password=request.password,
    )
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
    description="Authenticate with email and password to receive a JWT access token.",
)
def login(
    credentials: UserLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and return a signed JWT access token."""
    user = user_service.authenticate(
        db,
        email=credentials.email,
        password=credentials.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    access_token = create_access_token(
        subject=user.id,
        extra_claims={"email": user.email, "role": role_value},
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Current User Profile",
    description="Retrieve the profile of the currently authenticated user.",
)
def read_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Return authenticated user profile."""
    return current_user


# Protected endpoints for verifying role-based authorization
@router.get(
    "/admin-only",
    status_code=status.HTTP_200_OK,
    summary="Admin Protected Test Endpoint",
    description="Endpoint restricted strictly to administrators.",
)
def admin_only_endpoint(
    current_user: User = Depends(require_admin),
) -> dict[str, str]:
    """Admin-only verified route."""
    role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return {
        "message": f"Hello Admin {current_user.name}, you have full administrative access.",
        "role": role_str,
    }


@router.get(
    "/agent-only",
    status_code=status.HTTP_200_OK,
    summary="Support Agent and Admin Test Endpoint",
    description="Endpoint restricted to support agents and administrators.",
)
def agent_only_endpoint(
    current_user: User = Depends(require_agent_or_admin),
) -> dict[str, str]:
    """Agent and Admin verified route."""
    role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return {
        "message": f"Hello {current_user.name}, you have support staff access.",
        "role": role_str,
    }
