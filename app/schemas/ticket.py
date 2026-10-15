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
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1, max_length=255, description="Ticket title")
    description: str = Field(..., min_length=1, description="Detailed problem description")
    priority: TicketPriority = Field(TicketPriority.MEDIUM, description="Ticket priority")
    customer_id: Optional[int] = Field(None, description="Optional customer ID (Admin only)")


class TicketUpdate(BaseModel):
    """Payload for updating permitted ticket fields."""
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated title")
    description: Optional[str] = Field(None, min_length=1, description="Updated description")
    status: Optional[TicketStatus] = Field(None, description="Updated ticket status")
    priority: Optional[TicketPriority] = Field(None, description="Updated ticket priority")


class TicketAssignRequest(BaseModel):
    """Payload for assigning or unassigning a ticket to a support agent (Admin only)."""
    model_config = ConfigDict(extra="forbid")

    assigned_agent_id: Optional[int] = Field(
        ...,
        description="ID of the support agent to assign, or null to unassign",
    )


class TicketRead(TicketBase):
    """Public representation of a support ticket."""
    model_config = ConfigDict(from_attributes=True)

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
    items: List[TicketRead]
    total: int
    page: int
    page_size: int
    pages: int
