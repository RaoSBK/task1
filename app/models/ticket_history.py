"""Ticket history audit log database model."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
from app.models.enums import TicketStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.ticket import Ticket


class TicketHistory(Base):
    """Audit record capturing status transitions on support tickets."""

    __tablename__ = "ticket_history"
    __table_args__ = (
        CheckConstraint(
            "old_status IS NULL OR old_status IN ('open', 'in_progress', 'resolved', 'closed')",
            name="check_ticket_history_old_status",
        ),
        CheckConstraint(
            "new_status IN ('open', 'in_progress', 'resolved', 'closed')",
            name="check_ticket_history_new_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    changed_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status: Mapped[Optional[TicketStatus]] = mapped_column(
        String(20),
        nullable=True,
    )
    new_status: Mapped[TicketStatus] = mapped_column(
        String(20),
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="history")
    changed_by_user: Mapped["User"] = relationship("User", back_populates="ticket_history_entries")

    def __repr__(self) -> str:
        return (
            f"<TicketHistory id={self.id} ticket_id={self.ticket_id} "
            f"old_status={self.old_status!r} new_status={self.new_status!r}>"
        )
