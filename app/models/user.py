"""User database model."""

from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import String, DateTime, CheckConstraint, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.comment import Comment
    from app.models.ticket_history import TicketHistory


class User(Base):
    """User account entity with role-based access control."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('customer', 'agent', 'admin')",
            name="check_user_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            native_enum=False,
            length=20,
            values_callable=lambda x: [e.value for e in x],
            create_constraint=False,
        ),
        nullable=False,
        default=UserRole.CUSTOMER,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    tickets_created: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        back_populates="customer",
        foreign_keys="[Ticket.customer_id]",
        cascade="all, delete-orphan",
    )
    assigned_tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        back_populates="assigned_agent",
        foreign_keys="[Ticket.assigned_agent_id]",
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="author",
        foreign_keys="[Comment.author_id]",
        cascade="all, delete-orphan",
    )
    ticket_history_entries: Mapped[List["TicketHistory"]] = relationship(
        "TicketHistory",
        back_populates="changed_by_user",
        foreign_keys="[TicketHistory.changed_by]",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
