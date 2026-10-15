"""Comment Pydantic validation and serialization schemas."""

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class CommentBase(BaseModel):
    """Base fields shared across comment schemas."""
    body: str = Field(..., min_length=1)


class CommentCreate(CommentBase):
    """Payload for adding a comment to a ticket."""
    pass


class CommentRead(CommentBase):
    """Public representation of a ticket comment."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author_id: int
    created_at: datetime
