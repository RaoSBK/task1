"""Comment Pydantic validation and serialization schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.schemas.user import UserRead


class CommentCreate(BaseModel):
    """Payload for adding a comment to a ticket."""
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "body": "I have cleared my browser cache as requested, but the issue persists on Firefox.",
            }
        },
    )

    body: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Comment text (maximum 5,000 characters)",
    )

    @field_validator("body")
    @classmethod
    def validate_body_not_empty(cls, v: str) -> str:
        """Reject empty or whitespace-only messages."""
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Comment body cannot be empty or contain only whitespace.")
        return cleaned


class CommentRead(BaseModel):
    """Public representation of a ticket comment."""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 501,
                "ticket_id": 101,
                "author_id": 1,
                "body": "I have cleared my browser cache as requested, but the issue persists on Firefox.",
                "created_at": "2026-10-16T10:10:00Z",
                "author": {
                    "id": 1,
                    "name": "Jane Doe",
                    "email": "jane.doe@example.com",
                    "role": "customer",
                    "created_at": "2026-10-16T10:00:00Z",
                },
            }
        },
    )

    id: int
    ticket_id: int
    author_id: int
    body: str
    created_at: datetime
    author: Optional[UserRead] = None


class PaginatedCommentsResponse(BaseModel):
    """Paginated list of ticket comments."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": 501,
                        "ticket_id": 101,
                        "author_id": 1,
                        "body": "I have cleared my browser cache as requested, but the issue persists on Firefox.",
                        "created_at": "2026-10-16T10:10:00Z",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "pages": 1,
            }
        }
    )

    items: List[CommentRead]
    total: int
    page: int
    page_size: int
    pages: int
