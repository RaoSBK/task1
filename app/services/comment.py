"""Comment and ticket history service handling comments and audit logs."""

from datetime import datetime, timezone
import math
from typing import List, Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func

from app.models.ticket import Ticket
from app.models.comment import Comment
from app.models.ticket_history import TicketHistory
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.comment import CommentCreate
from app.services.base import BaseService


class CommentService(BaseService[Comment]):
    """Service encapsulating ticket comments and history retrieval."""

    def __init__(self):
        super().__init__(Comment)

    def _verify_ticket_access(self, *, ticket: Ticket, current_user: User) -> None:
        """Verify user has permission to view or comment on this ticket."""
        if current_user.role == UserRole.ADMIN:
            return

        if current_user.role == UserRole.AGENT:
            if ticket.assigned_agent_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agents can only access comments and history for tickets assigned to them.",
                )
            return

        if current_user.role == UserRole.CUSTOMER:
            if ticket.customer_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Customers can only access comments and history for their own tickets.",
                )
            return

    def create_comment(
        self,
        db: Session,
        *,
        ticket_id: int,
        current_user: User,
        data: CommentCreate,
    ) -> Comment:
        """Add a comment to a ticket, strictly setting author_id to authenticated user."""
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket with ID {ticket_id} not found.",
            )

        self._verify_ticket_access(ticket=ticket, current_user=current_user)

        try:
            comment = Comment(
                ticket_id=ticket.id,
                author_id=current_user.id,  # Strictly derived from authenticated user
                body=data.body.strip(),
            )
            # Update ticket updated_at timestamp when a comment is added using database clock
            ticket.updated_at = func.now()

            db.add(comment)
            db.commit()
            db.refresh(comment)
            db.refresh(ticket)
        except Exception:
            db.rollback()
            raise

        # Load author relationship to avoid N+1 queries
        statement = (
            select(Comment)
            .options(joinedload(Comment.author))
            .where(Comment.id == comment.id)
        )
        loaded = db.scalar(statement)
        return loaded or comment

    def list_comments(
        self,
        db: Session,
        *,
        ticket_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Comment], int, int]:
        """Retrieve comments in chronological order with pagination and eager loading."""
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket with ID {ticket_id} not found.",
            )

        self._verify_ticket_access(ticket=ticket, current_user=current_user)

        count_stmt = select(func.count(Comment.id)).where(Comment.ticket_id == ticket.id)
        total = db.scalar(count_stmt) or 0
        pages = math.ceil(total / page_size) if total > 0 else 0

        # Retrieve in ascending chronological order
        statement = (
            select(Comment)
            .options(joinedload(Comment.author))
            .where(Comment.ticket_id == ticket.id)
            .order_by(Comment.created_at.asc(), Comment.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(db.scalars(statement).unique().all())
        return items, total, pages

    def list_ticket_history(
        self,
        db: Session,
        *,
        ticket_id: int,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[TicketHistory], int, int]:
        """Retrieve ticket audit history in chronological order with pagination."""
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket with ID {ticket_id} not found.",
            )

        self._verify_ticket_access(ticket=ticket, current_user=current_user)

        count_stmt = select(func.count(TicketHistory.id)).where(
            TicketHistory.ticket_id == ticket.id
        )
        total = db.scalar(count_stmt) or 0
        pages = math.ceil(total / page_size) if total > 0 else 0

        statement = (
            select(TicketHistory)
            .options(joinedload(TicketHistory.changed_by_user))
            .where(TicketHistory.ticket_id == ticket.id)
            .order_by(TicketHistory.changed_at.asc(), TicketHistory.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(db.scalars(statement).unique().all())
        return items, total, pages


comment_service = CommentService()
