"""Pydantic schemas package."""

from app.schemas.enums import UserRole, TicketStatus, TicketPriority
from app.schemas.health import HealthCheckResponse
from app.schemas.user import (
    UserBase,
    UserCreate,
    UserRead,
    CustomerRegisterRequest,
    UserLoginRequest,
    TokenResponse,
)
from app.schemas.ticket import (
    TicketBase,
    TicketCreate,
    TicketUpdate,
    TicketAssignRequest,
    TicketRead,
    PaginatedTicketsResponse,
)
from app.schemas.comment import CommentBase, CommentCreate, CommentRead
from app.schemas.ticket_history import TicketHistoryRead

__all__ = [
    "UserRole",
    "TicketStatus",
    "TicketPriority",
    "HealthCheckResponse",
    "UserBase",
    "UserCreate",
    "UserRead",
    "CustomerRegisterRequest",
    "UserLoginRequest",
    "TokenResponse",
    "TicketBase",
    "TicketCreate",
    "TicketUpdate",
    "TicketAssignRequest",
    "TicketRead",
    "PaginatedTicketsResponse",
    "CommentBase",
    "CommentCreate",
    "CommentRead",
    "TicketHistoryRead",
]
