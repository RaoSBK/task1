"""Ticket database model."""

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
from app.models.enums import TicketStatus, TicketPriority

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.comment import Comment
    from app.models.ticket_history import TicketHistory


class Ticket(Base):
    """Customer support ticket entity."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'closed')",
            name="check_ticket_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="check_ticket_priority",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        String(20),
        nullable=False,
        default=TicketStatus.OPEN,
        index=True,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        String(20),
        nullable=False,
        default=TicketPriority.MEDIUM,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    customer: Mapped["User"] = relationship(
        "User",
        back_populates="tickets_created",
        foreign_keys=[customer_id],
    )
    assigned_agent: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="assigned_tickets",
        foreign_keys=[assigned_agent_id],
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="Comment.created_at.asc()",
    )
    history: Mapped[List["TicketHistory"]] = relationship(
        "TicketHistory",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketHistory.changed_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} title={self.title!r} status={self.status!r} priority={self.priority!r}>"
