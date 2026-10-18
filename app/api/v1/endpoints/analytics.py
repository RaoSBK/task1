"""Analytics endpoints for ticket status metrics and agent workload rankings."""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.analytics import TicketStatusCountsResponse, AgentUnresolvedTickets
from app.services.analytics import analytics_service

router = APIRouter()


@router.get(
    "/tickets/status-counts",
    response_model=TicketStatusCountsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket Counts by Status",
    description=(
        "Retrieve aggregate ticket counts broken down across all supported statuses "
        "(open, in_progress, resolved, closed). Zero-ticket statuses are explicitly reported. "
        "Access is restricted to administrators."
    ),
)
def get_ticket_status_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TicketStatusCountsResponse:
    """Return count of tickets in each supported status, including statuses with zero tickets."""
    return analytics_service.get_status_counts(db)


@router.get(
    "/agents/unresolved",
    response_model=List[AgentUnresolvedTickets],
    status_code=status.HTTP_200_OK,
    summary="Rank Agents by Unresolved Tickets",
    description=(
        "Rank support agents by the count of unresolved tickets (open or in_progress) "
        "assigned to them. Agents with zero unresolved tickets are preserved. "
        "Access is restricted to administrators."
    ),
)
def get_unresolved_agents_ranking(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> List[AgentUnresolvedTickets]:
    """Rank agents by unresolved assigned tickets in descending order."""
    return analytics_service.get_unresolved_agents_ranking(db)
