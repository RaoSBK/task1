"""Ticket management API endpoints."""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_admin
from app.models.user import User
from app.models.enums import TicketStatus, TicketPriority
from app.schemas.ticket import (
    TicketCreate,
    TicketUpdate,
    TicketAssignRequest,
    TicketRead,
    PaginatedTicketsResponse,
)
from app.schemas.comment import CommentCreate, CommentRead, PaginatedCommentsResponse
from app.schemas.ticket_history import PaginatedTicketHistoryResponse
from app.services.ticket import ticket_service
from app.services.comment import comment_service

router = APIRouter()


@router.post(
    "",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Ticket",
    description=(
        "Create a new support ticket. Customers can only create tickets for themselves. "
        "Tickets start in 'open' status and are initially unassigned."
    ),
)
def create_ticket(
    request: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketRead:
    """Create a support ticket."""
    return ticket_service.create_ticket(db, current_user=current_user, data=request)


@router.get(
    "",
    response_model=PaginatedTicketsResponse,
    status_code=status.HTTP_200_OK,
    summary="List Tickets",
    description=(
        "List tickets with pagination and filtering. "
        "Customers only see their own tickets. "
        "Agents only see tickets assigned to them. "
        "Administrators see all tickets."
    ),
)
def list_tickets(
    status_filter: Optional[TicketStatus] = Query(None, alias="status", description="Filter by status"),
    priority_filter: Optional[TicketPriority] = Query(None, alias="priority", description="Filter by priority"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID (Admin only)"),
    assigned_agent_id: Optional[int] = Query(None, description="Filter by assigned agent ID (Admin only)"),
    created_after: Optional[datetime] = Query(None, description="Filter by created on or after UTC datetime"),
    created_before: Optional[datetime] = Query(None, description="Filter by created on or before UTC datetime"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1 to 100, default 20)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedTicketsResponse:
    """List tickets with role-based filtering and pagination."""
    items, total, pages = ticket_service.list_tickets(
        db,
        current_user=current_user,
        status_filter=status_filter,
        priority_filter=priority_filter,
        customer_id=customer_id,
        assigned_agent_id=assigned_agent_id,
        created_after=created_after,
        created_before=created_before,
        page=page,
        page_size=page_size,
    )
    return PaginatedTicketsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketRead,
    status_code=status.HTTP_200_OK,
    summary="Get Ticket by ID",
    description="Retrieve a single support ticket by its ID, enforcing role-based access control.",
)
def get_ticket(
    ticket_id: int = Path(..., ge=1, description="ID of the ticket to retrieve"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketRead:
    """Retrieve a single ticket."""
    ticket = ticket_service.get_ticket_by_id(db, ticket_id=ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with ID {ticket_id} not found.",
        )
    ticket_service.verify_ticket_access(ticket=ticket, current_user=current_user)
    return ticket


@router.patch(
    "/{ticket_id}",
    response_model=TicketRead,
    status_code=status.HTTP_200_OK,
    summary="Update Ticket",
    description=(
        "Update permitted ticket fields. Customers can only update title and description "
        "of their own tickets. Agents can update status and priority of their assigned tickets. "
        "Admins can update any permitted field."
    ),
)
def update_ticket(
    request: TicketUpdate,
    ticket_id: int = Path(..., ge=1, description="ID of the ticket to update"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketRead:
    """Update permitted fields on a support ticket."""
    ticket = ticket_service.get_ticket_by_id(db, ticket_id=ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with ID {ticket_id} not found.",
        )
    return ticket_service.update_ticket(
        db,
        ticket=ticket,
        current_user=current_user,
        data=request,
    )


@router.patch(
    "/{ticket_id}/assign",
    response_model=TicketRead,
    status_code=status.HTTP_200_OK,
    summary="Assign Ticket to Support Agent",
    description="Assign a ticket to a support agent or unassign it (Admin only).",
)
def assign_ticket(
    request: TicketAssignRequest,
    ticket_id: int = Path(..., ge=1, description="ID of the ticket to assign"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TicketRead:
    """Assign ticket to a support agent."""
    ticket = ticket_service.get_ticket_by_id(db, ticket_id=ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with ID {ticket_id} not found.",
        )
    return ticket_service.assign_ticket(
        db,
        ticket=ticket,
        current_user=current_user,
        data=request,
    )


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add Comment to Ticket",
    description=(
        "Add a comment to a ticket. author_id is strictly derived from the authenticated user. "
        "Customers can only comment on their own tickets. "
        "Agents can only comment on tickets assigned to them. "
        "Admins can comment on any ticket."
    ),
)
def add_comment(
    request: CommentCreate,
    ticket_id: int = Path(..., ge=1, description="ID of the ticket to comment on"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentRead:
    """Add a comment to a support ticket."""
    return comment_service.create_comment(
        db,
        ticket_id=ticket_id,
        current_user=current_user,
        data=request,
    )


@router.get(
    "/{ticket_id}/comments",
    response_model=PaginatedCommentsResponse,
    status_code=status.HTTP_200_OK,
    summary="List Ticket Comments",
    description=(
        "Retrieve comments for a ticket in ascending chronological order with pagination. "
        "Enforces the same ownership rules: customers only access own tickets; "
        "agents only access assigned tickets; admins access all."
    ),
)
def list_ticket_comments(
    ticket_id: int = Path(..., ge=1, description="ID of the ticket"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedCommentsResponse:
    """List comments for a ticket in chronological order."""
    items, total, pages = comment_service.list_comments(
        db,
        ticket_id=ticket_id,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )
    return PaginatedCommentsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{ticket_id}/history",
    response_model=PaginatedTicketHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="List Ticket Audit History",
    description="Retrieve status transition history for a ticket in chronological order.",
)
def list_ticket_history(
    ticket_id: int = Path(..., ge=1, description="ID of the ticket"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedTicketHistoryResponse:
    """List status change audit history for a ticket."""
    items, total, pages = comment_service.list_ticket_history(
        db,
        ticket_id=ticket_id,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )
    return PaginatedTicketHistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
