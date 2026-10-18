"""Analytics service for ticket reporting and agent workload aggregation."""

from typing import List, Dict
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.ticket import Ticket
from app.models.enums import UserRole, TicketStatus
from app.schemas.analytics import TicketStatusCountsResponse, AgentUnresolvedTickets


class AnalyticsService:
    """Service providing aggregate reporting on tickets and agent workloads."""

    def get_status_counts(self, db: Session) -> TicketStatusCountsResponse:
        """Report the number of tickets in each supported status, including statuses with zero tickets.

        Uses database-side aggregation (GROUP BY status) and guarantees deterministic
        reporting of all supported TicketStatus values.
        """
        stmt = (
            select(
                Ticket.status,
                func.count(Ticket.id).label("count"),
            )
            .group_by(Ticket.status)
        )
        results = db.execute(stmt).all()

        # Initialize all supported statuses with 0 so statuses with no tickets are present
        counts: Dict[str, int] = {status.value: 0 for status in TicketStatus}
        for row in results:
            status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
            counts[status_val] = row.count

        total = sum(counts.values())

        return TicketStatusCountsResponse(
            open=counts.get(TicketStatus.OPEN.value, 0),
            in_progress=counts.get(TicketStatus.IN_PROGRESS.value, 0),
            resolved=counts.get(TicketStatus.RESOLVED.value, 0),
            closed=counts.get(TicketStatus.CLOSED.value, 0),
            total=total,
            counts=counts,
            status_counts=counts,
        )

    def get_unresolved_agents_ranking(self, db: Session) -> List[AgentUnresolvedTickets]:
        """Rank agents by the number of unresolved tickets assigned to them.

        Unresolved tickets are defined as tickets with status 'open' or 'in_progress'.
        Agents with zero unresolved tickets are preserved via an appropriate LEFT JOIN
        where the status filter is in the join condition.

        Ordering is deterministic:
        ORDER BY unresolved_count DESC, user.name ASC, user.id ASC.
        """
        unresolved_statuses = [TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value]

        stmt = (
            select(
                User.id.label("agent_id"),
                User.name,
                User.email,
                func.count(Ticket.id).label("unresolved_count"),
                func.count(Ticket.id)
                .filter(Ticket.status == TicketStatus.OPEN.value)
                .label("open_count"),
                func.count(Ticket.id)
                .filter(Ticket.status == TicketStatus.IN_PROGRESS.value)
                .label("in_progress_count"),
            )
            .outerjoin(
                Ticket,
                and_(
                    Ticket.assigned_agent_id == User.id,
                    Ticket.status.in_(unresolved_statuses),
                ),
            )
            .where(User.role == UserRole.AGENT.value)
            .group_by(User.id, User.name, User.email)
            .order_by(
                func.count(Ticket.id).desc(),
                User.name.asc(),
                User.id.asc(),
            )
        )
        rows = db.execute(stmt).all()

        return [
            AgentUnresolvedTickets(
                agent_id=row.agent_id,
                id=row.agent_id,
                name=row.name,
                email=row.email,
                unresolved_count=row.unresolved_count,
                open_count=row.open_count or 0,
                in_progress_count=row.in_progress_count or 0,
            )
            for row in rows
        ]


analytics_service = AnalyticsService()
