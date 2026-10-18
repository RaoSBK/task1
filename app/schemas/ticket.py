"""Ticket Pydantic validation and serialization schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.enums import TicketStatus, TicketPriority
from app.schemas.user import UserRead


class TicketBase(BaseModel):
    """Base fields shared across ticket schemas."""
    title: str = Field(..., min_length=1, max_length=255, description="Ticket title")
    description: str = Field(..., min_length=1, description="Detailed problem description")
    priority: TicketPriority = Field(TicketPriority.MEDIUM, description="Ticket priority")


class TicketCreate(BaseModel):
    """Payload for creating a new support ticket.

    Note: Customers are strictly forbidden from assigning tickets upon creation.
    customer_id can only be specified by administrators.
    """
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "title": "Cannot access billing portal",
                "description": "Receiving a 403 Forbidden error when trying to view invoices.",
                "priority": "high",
            }
        },
    )

    title: str = Field(..., min_length=1, max_length=255, description="Ticket title")
    description: str = Field(..., min_length=1, description="Detailed problem description")
    priority: TicketPriority = Field(TicketPriority.MEDIUM, description="Ticket priority")
    customer_id: Optional[int] = Field(None, description="Optional customer ID (Admin only)")


class TicketUpdate(BaseModel):
    """Payload for updating permitted ticket fields."""
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "title": "Billing portal access issue (Resolved after cache clear)",
                "status": "in_progress",
                "priority": "medium",
            }
        },
    )

    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated title")
    description: Optional[str] = Field(None, min_length=1, description="Updated description")
    status: Optional[TicketStatus] = Field(None, description="Updated ticket status")
    priority: Optional[TicketPriority] = Field(None, description="Updated ticket priority")


class TicketAssignRequest(BaseModel):
    """Payload for assigning or unassigning a ticket to a support agent (Admin only)."""
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "assigned_agent_id": 2,
            }
        },
    )

    assigned_agent_id: Optional[int] = Field(
        ...,
        description="ID of the support agent to assign, or null to unassign",
    )


class TicketRead(TicketBase):
    """Public representation of a support ticket."""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 101,
                "title": "Cannot access billing portal",
                "description": "Receiving a 403 Forbidden error when trying to view invoices.",
                "priority": "high",
                "status": "open",
                "customer_id": 1,
                "assigned_agent_id": 2,
                "created_at": "2026-10-16T10:00:00Z",
                "updated_at": "2026-10-16T10:15:00Z",
            }
        },
    )

    id: int
    customer_id: int
    assigned_agent_id: Optional[int] = None
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    customer: Optional[UserRead] = None
    assigned_agent: Optional[UserRead] = None


class PaginatedTicketsResponse(BaseModel):
    """Paginated list of support tickets."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": 101,
                        "title": "Cannot access billing portal",
                        "description": "Receiving a 403 Forbidden error when trying to view invoices.",
                        "priority": "high",
                        "status": "open",
                        "customer_id": 1,
                        "assigned_agent_id": 2,
                        "created_at": "2026-10-16T10:00:00Z",
                        "updated_at": "2026-10-16T10:15:00Z",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "pages": 1,
            }
        }
    )

    items: List[TicketRead]
    total: int
    page: int
    page_size: int
    pages: int
