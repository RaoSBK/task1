"""Pydantic schemas for ticket analytics and agent workload reporting."""

from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class TicketStatusCountsResponse(BaseModel):
    """Aggregate ticket counts broken down by status."""

    open: int = Field(default=0, description="Count of open tickets")
    in_progress: int = Field(default=0, description="Count of in-progress tickets")
    resolved: int = Field(default=0, description="Count of resolved tickets")
    closed: int = Field(default=0, description="Count of closed tickets")
    total: int = Field(default=0, description="Total count across all statuses")
    counts: Dict[str, int] = Field(default_factory=dict, description="Status-to-count mapping")
    status_counts: Dict[str, int] = Field(default_factory=dict, description="Alias status-to-count mapping")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "open": 5,
                "in_progress": 2,
                "resolved": 10,
                "closed": 4,
                "total": 21,
                "counts": {
                    "open": 5,
                    "in_progress": 2,
                    "resolved": 10,
                    "closed": 4,
                },
                "status_counts": {
                    "open": 5,
                    "in_progress": 2,
                    "resolved": 10,
                    "closed": 4,
                },
            }
        },
    )


class AgentUnresolvedTickets(BaseModel):
    """Support agent ranked by count of unresolved assigned tickets."""

    agent_id: int = Field(..., description="Unique ID of the support agent")
    id: Optional[int] = Field(None, description="Alias for agent_id")
    name: str = Field(..., description="Full name of the support agent")
    email: str = Field(..., description="Email address of the support agent")
    unresolved_count: int = Field(default=0, description="Total unresolved tickets (open + in_progress)")
    open_count: int = Field(default=0, description="Number of open tickets assigned")
    in_progress_count: int = Field(default=0, description="Number of in-progress tickets assigned")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "agent_id": 2,
                "id": 2,
                "name": "Sarah Agent",
                "email": "sarah.agent@example.com",
                "unresolved_count": 7,
                "open_count": 4,
                "in_progress_count": 3,
            }
        },
    )
