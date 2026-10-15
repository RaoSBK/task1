"""Comment database model."""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    Text,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.ticket import Ticket


class Comment(Base):
    """Comment on a support ticket."""

    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="comments")
    author: Mapped["User"] = relationship("User", back_populates="comments")

    def __repr__(self) -> str:
        return f"<Comment id={self.id} ticket_id={self.ticket_id} author_id={self.author_id}>"
