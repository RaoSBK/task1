"""Ticket service encapsulating ticket business logic, RBAC, and queries."""

from datetime import datetime, timezone
import math
from typing import Optional, List, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func

from app.models.ticket import Ticket
from app.models.ticket_history import TicketHistory
from app.models.user import User
from app.models.enums import UserRole, TicketStatus, TicketPriority
from app.schemas.ticket import TicketCreate, TicketUpdate, TicketAssignRequest
from app.services.base import BaseService


class TicketService(BaseService[Ticket]):
    """Service handling ticket creation, retrieval, updates, and assignment."""

    def __init__(self):
        super().__init__(Ticket)

    def create_ticket(
        self, db: Session, *, current_user: User, data: TicketCreate
    ) -> Ticket:
        """Create a new ticket with appropriate customer ownership."""
        if current_user.role == UserRole.ADMIN and data.customer_id is not None:
            # Admin creating on behalf of a specific customer
            target_customer = db.get(User, data.customer_id)
            if not target_customer:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Customer with ID {data.customer_id} does not exist.",
                )
            customer_id = target_customer.id
        else:
            # Customers (and agents creating for themselves) are set as ticket owner
            customer_id = current_user.id

        ticket = Ticket(
            customer_id=customer_id,
            assigned_agent_id=None,  # Tickets start unassigned
            title=data.title.strip(),
            description=data.description.strip(),
            priority=data.priority,
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        db.flush()  # Flush to obtain ticket.id for history record

        # Log initial creation audit history
        history = TicketHistory(
            ticket_id=ticket.id,
            changed_by=current_user.id,
            old_status=None,
            new_status=TicketStatus.OPEN,
        )
        db.add(history)
        db.commit()
        db.refresh(ticket)
        return ticket

    def get_ticket_by_id(
        self, db: Session, *, ticket_id: int
    ) -> Optional[Ticket]:
        """Fetch a single ticket with customer and agent relationships loaded to prevent N+1 queries."""
        statement = (
            select(Ticket)
            .options(
                joinedload(Ticket.customer),
                joinedload(Ticket.assigned_agent),
            )
            .where(Ticket.id == ticket_id)
        )
        return db.scalar(statement)

    def verify_ticket_access(
        self, *, ticket: Ticket, current_user: User
    ) -> None:
        """Verify current user has permission to view or access this ticket."""
        if current_user.role == UserRole.ADMIN:
            return  # Admins have global access

        if current_user.role == UserRole.AGENT:
            if ticket.assigned_agent_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to access tickets not assigned to you.",
                )
            return

        if current_user.role == UserRole.CUSTOMER:
            if ticket.customer_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to access other customers' tickets.",
                )
            return

    def list_tickets(
        self,
        db: Session,
        *,
        current_user: User,
        status_filter: Optional[TicketStatus] = None,
        priority_filter: Optional[TicketPriority] = None,
        customer_id: Optional[int] = None,
        assigned_agent_id: Optional[int] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Ticket], int, int]:
        """List tickets with role-based scoping, filtering, and pagination."""
        statement = select(Ticket).options(
            joinedload(Ticket.customer),
            joinedload(Ticket.assigned_agent),
        )
        count_stmt = select(func.count(Ticket.id))

        # Enforce role-based scoping
        if current_user.role == UserRole.CUSTOMER:
            # Customers are strictly restricted to their own tickets
            if customer_id is not None and customer_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Customers cannot filter by other customers' IDs.",
                )
            if assigned_agent_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Customers are not authorized to filter by assigned agent.",
                )
            statement = statement.where(Ticket.customer_id == current_user.id)
            count_stmt = count_stmt.where(Ticket.customer_id == current_user.id)

        elif current_user.role == UserRole.AGENT:
            # Agents can only view tickets assigned to them
            if assigned_agent_id is not None and assigned_agent_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agents cannot view tickets assigned to other agents.",
                )
            statement = statement.where(Ticket.assigned_agent_id == current_user.id)
            count_stmt = count_stmt.where(Ticket.assigned_agent_id == current_user.id)

            if customer_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agents are not authorized to filter by customer ID.",
                )

        elif current_user.role == UserRole.ADMIN:
            # Admins have global visibility with optional filters
            if customer_id is not None:
                statement = statement.where(Ticket.customer_id == customer_id)
                count_stmt = count_stmt.where(Ticket.customer_id == customer_id)
            if assigned_agent_id is not None:
                statement = statement.where(Ticket.assigned_agent_id == assigned_agent_id)
                count_stmt = count_stmt.where(Ticket.assigned_agent_id == assigned_agent_id)

        # Apply common filters
        if status_filter is not None:
            statement = statement.where(Ticket.status == status_filter)
            count_stmt = count_stmt.where(Ticket.status == status_filter)

        if priority_filter is not None:
            statement = statement.where(Ticket.priority == priority_filter)
            count_stmt = count_stmt.where(Ticket.priority == priority_filter)

        if created_after is not None:
            statement = statement.where(Ticket.created_at >= created_after)
            count_stmt = count_stmt.where(Ticket.created_at >= created_after)

        if created_before is not None:
            statement = statement.where(Ticket.created_at <= created_before)
            count_stmt = count_stmt.where(Ticket.created_at <= created_before)

        # Count total matching records
        total = db.scalar(count_stmt) or 0
        pages = math.ceil(total / page_size) if total > 0 else 0

        # Order by newest first and paginate
        statement = (
            statement.order_by(Ticket.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(db.scalars(statement).unique().all())
        return items, total, pages

    def update_ticket(
        self,
        db: Session,
        *,
        ticket: Ticket,
        current_user: User,
        data: TicketUpdate,
    ) -> Ticket:
        """Update permitted ticket fields according to user role permissions."""
        if current_user.role == UserRole.CUSTOMER:
            if ticket.customer_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to update this ticket.",
                )
            # Customers cannot change privileged fields: status or priority
            if data.status is not None or data.priority is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Customers are not permitted to change ticket status or priority.",
                )

        elif current_user.role == UserRole.AGENT:
            if ticket.assigned_agent_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agents can only update tickets assigned to them.",
                )

        # Admins can update any ticket

        try:
            # Check for status transition and log history atomically
            old_status = ticket.status
            if data.status is not None and data.status != old_status:
                ticket.status = data.status
                history = TicketHistory(
                    ticket_id=ticket.id,
                    changed_by=current_user.id,
                    old_status=old_status,
                    new_status=data.status,
                )
                db.add(history)

            if data.title is not None:
                ticket.title = data.title.strip()
            if data.description is not None:
                ticket.description = data.description.strip()
            if data.priority is not None:
                ticket.priority = data.priority

            # Update updated_at timestamp
            ticket.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(ticket)
            return ticket
        except Exception:
            db.rollback()
            raise

    def assign_ticket(
        self,
        db: Session,
        *,
        ticket: Ticket,
        current_user: User,
        data: TicketAssignRequest,
    ) -> Ticket:
        """Assign or unassign a ticket to a support agent (Admin only)."""
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators are permitted to assign tickets.",
            )

        if data.assigned_agent_id is not None:
            agent = db.get(User, data.assigned_agent_id)
            if not agent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {data.assigned_agent_id} does not exist.",
                )
            if agent.role != UserRole.AGENT:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot assign ticket to user with role '{agent.role.value if hasattr(agent.role, 'value') else agent.role}'. "
                        "Tickets can only be assigned to users with the 'agent' role."
                    ),
                )
            ticket.assigned_agent_id = agent.id
        else:
            ticket.assigned_agent_id = None

        ticket.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(ticket)
        return ticket


ticket_service = TicketService()
