"""Ticket history Pydantic validation and serialization schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.enums import TicketStatus


class TicketHistoryRead(BaseModel):
    """Public representation of an audit history transition log entry."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    changed_by: int
    old_status: Optional[TicketStatus] = None
    new_status: TicketStatus
    changed_at: datetime
