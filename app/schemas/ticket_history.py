"""Ticket history Pydantic validation and serialization schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.schemas.enums import TicketStatus
from app.schemas.user import UserRead


class TicketHistoryRead(BaseModel):
    """Public representation of an audit history transition log entry."""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "ticket_id": 101,
                "changed_by": 2,
                "old_status": "open",
                "new_status": "in_progress",
                "changed_at": "2026-10-16T10:15:00Z",
                "changed_by_user": {
                    "id": 2,
                    "name": "Support Agent",
                    "email": "agent@example.com",
                    "role": "agent",
                    "created_at": "2026-10-16T09:00:00Z",
                },
            }
        },
    )

    id: int
    ticket_id: int
    changed_by: int
    old_status: Optional[TicketStatus] = None
    new_status: TicketStatus
    changed_at: datetime
    changed_by_user: Optional[UserRead] = None


class PaginatedTicketHistoryResponse(BaseModel):
    """Paginated list of ticket history transition records."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": 1,
                        "ticket_id": 101,
                        "changed_by": 2,
                        "old_status": "open",
                        "new_status": "in_progress",
                        "changed_at": "2026-10-16T10:15:00Z",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "pages": 1,
            }
        }
    )

    items: List[TicketHistoryRead]
    total: int
    page: int
    page_size: int
    pages: int
