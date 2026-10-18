"""Tests for ticket comments, chronological retrieval, permissions, history, and transaction atomicity."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole, TicketStatus, TicketPriority
from app.models.user import User
from app.models.ticket import Ticket
from app.models.comment import Comment
from app.models.ticket_history import TicketHistory
from app.services.user import user_service
from app.services.ticket import ticket_service
from app.services.comment import comment_service
from app.core.security import create_access_token


def create_user_token(
    db_session: Session,
    *,
    name: str,
    email: str,
    role: UserRole = UserRole.CUSTOMER,
) -> tuple[int, str]:
    """Helper creating user and returning (user_id, jwt_token)."""
    user = user_service.create_user_with_role(
        db_session,
        name=name,
        email=email,
        password="ValidPassword123!",
        role=role,
    )
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(subject=user.id, extra_claims={"email": user.email, "role": role_str})
    return user.id, token


def test_customer_create_comment_success(client: TestClient, db_session: Session):
    """Verify customer can comment on their own ticket and author_id is correctly set."""
    cust_id, cust_token = create_user_token(db_session, name="Comment Cust", email="comm_cust@example.com")
    ticket = Ticket(customer_id=cust_id, title="Ticket with Comments", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    initial_updated_at = ticket.updated_at

    payload = {"body": "Thank you for looking into this, here are the logs."}
    response = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json=payload,
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["body"] == payload["body"]
    assert data["ticket_id"] == ticket.id
    assert data["author_id"] == cust_id
    assert "id" in data
    assert "created_at" in data

    # Verify ticket updated_at was bumped
    db_session.refresh(ticket)
    assert ticket.updated_at >= initial_updated_at


def test_comment_author_id_strictly_derived_from_authenticated_user(client: TestClient, db_session: Session):
    """Verify author_id passed in payload is completely ignored in favor of authenticated user."""
    cust_id, cust_token = create_user_token(db_session, name="Impersonator", email="impersonator@example.com")
    ticket = Ticket(customer_id=cust_id, title="Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    # Client tries to pass a forged author_id (e.g. 9999 or admin)
    payload = {
        "body": "Comment trying to spoof author",
        "author_id": 9999,
    }
    response = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json=payload,
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["author_id"] == cust_id  # Authenticated user ID is strictly enforced


def test_comment_content_validation_rejects_empty_and_whitespace(client: TestClient, db_session: Session):
    """Verify empty or whitespace-only comment body is rejected with 422."""
    cust_id, cust_token = create_user_token(db_session, name="Empty Comm Cust", email="empty_comm@example.com")
    ticket = Ticket(customer_id=cust_id, title="Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    # Empty string
    r1 = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": ""},
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert r1.status_code == 422

    # Whitespace only
    r2 = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": "   \n\t   "},
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert r2.status_code == 422


def test_comment_content_validation_rejects_excessively_long_message(client: TestClient, db_session: Session):
    """Verify comment body exceeding 5,000 characters is rejected with 422."""
    cust_id, cust_token = create_user_token(db_session, name="Long Comm Cust", email="long_comm@example.com")
    ticket = Ticket(customer_id=cust_id, title="Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    long_body = "x" * 5001
    response = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": long_body},
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert response.status_code == 422


def test_customer_cannot_comment_on_other_customer_ticket(client: TestClient, db_session: Session):
    """Verify customer cannot comment on another customer's ticket -> 403 Forbidden."""
    owner_id, _ = create_user_token(db_session, name="Owner Cust", email="owner_c@example.com")
    _, intruder_token = create_user_token(db_session, name="Intruder Cust", email="intruder_c@example.com")

    ticket = Ticket(customer_id=owner_id, title="Owner Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    response = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": "Intruding comment"},
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert response.status_code == 403
    assert "own tickets" in response.json()["detail"].lower()


def test_agent_comment_permissions(client: TestClient, db_session: Session):
    """Verify agent can comment only on tickets assigned to them."""
    cust_id, _ = create_user_token(db_session, name="Agent Comm Cust", email="ag_comm_c@example.com")
    agent_1_id, agent_1_token = create_user_token(db_session, name="Comm Agent 1", email="comm_ag1@example.com", role=UserRole.AGENT)
    _, agent_2_token = create_user_token(db_session, name="Comm Agent 2", email="comm_ag2@example.com", role=UserRole.AGENT)

    ticket = Ticket(customer_id=cust_id, assigned_agent_id=agent_1_id, title="Assigned Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    # 1. Assigned Agent 1 can comment -> 201 Created
    r_assigned = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": "Agent 1 response: investigating now."},
        headers={"Authorization": f"Bearer {agent_1_token}"},
    )
    assert r_assigned.status_code == 201

    # 2. Unassigned Agent 2 cannot comment -> 403 Forbidden
    r_unassigned = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": "Agent 2 trying to comment"},
        headers={"Authorization": f"Bearer {agent_2_token}"},
    )
    assert r_unassigned.status_code == 403
    assert "assigned to them" in r_unassigned.json()["detail"].lower()


def test_admin_can_comment_on_any_ticket(client: TestClient, db_session: Session):
    """Verify administrator can comment on any ticket."""
    cust_id, _ = create_user_token(db_session, name="Admin Comm Cust", email="ad_comm_c@example.com")
    _, admin_token = create_user_token(db_session, name="Admin Commenter", email="ad_commenter@example.com", role=UserRole.ADMIN)

    ticket = Ticket(customer_id=cust_id, title="Any Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    response = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": "Admin executive update."},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201


def test_chronological_comments_retrieval_and_pagination(client: TestClient, db_session: Session):
    """Verify comments are retrieved in strictly chronological order with pagination."""
    cust_id, cust_token = create_user_token(db_session, name="Chrono Cust", email="chrono_c@example.com")
    ticket = Ticket(customer_id=cust_id, title="Chrono Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    # Add 5 comments sequentially
    for i in range(1, 6):
        client.post(
            f"/api/v1/tickets/{ticket.id}/comments",
            json={"body": f"Comment #{i}"},
            headers={"Authorization": f"Bearer {cust_token}"},
        )

    # Fetch page 1 with page_size=3
    r_page1 = client.get(
        f"/api/v1/tickets/{ticket.id}/comments?page=1&page_size=3",
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert r_page1.status_code == 200
    data1 = r_page1.json()
    assert len(data1["items"]) == 3
    assert data1["items"][0]["body"] == "Comment #1"
    assert data1["items"][1]["body"] == "Comment #2"
    assert data1["items"][2]["body"] == "Comment #3"
    assert data1["total"] == 5
    assert data1["pages"] == 2

    # Fetch page 2 with page_size=3
    r_page2 = client.get(
        f"/api/v1/tickets/{ticket.id}/comments?page=2&page_size=3",
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert r_page2.status_code == 200
    data2 = r_page2.json()
    assert len(data2["items"]) == 2
    assert data2["items"][0]["body"] == "Comment #4"
    assert data2["items"][1]["body"] == "Comment #5"


def test_guessed_ticket_id_access_prevention(client: TestClient, db_session: Session):
    """Verify unauthorized users cannot view comments or history of other or non-existent tickets."""
    owner_id, _ = create_user_token(db_session, name="Guess Owner", email="guess_owner@example.com")
    _, intruder_token = create_user_token(db_session, name="Guesser", email="guesser@example.com")

    ticket = Ticket(customer_id=owner_id, title="Protected Ticket", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    # 1. Nonexistent ticket -> 404
    assert client.get("/api/v1/tickets/999999/comments", headers={"Authorization": f"Bearer {intruder_token}"}).status_code == 404
    assert client.get("/api/v1/tickets/999999/history", headers={"Authorization": f"Bearer {intruder_token}"}).status_code == 404
    assert client.post("/api/v1/tickets/999999/comments", json={"body": "Hello"}, headers={"Authorization": f"Bearer {intruder_token}"}).status_code == 404

    # 2. Existing ticket belonging to another customer -> 403 Forbidden
    r_comm = client.get(f"/api/v1/tickets/{ticket.id}/comments", headers={"Authorization": f"Bearer {intruder_token}"})
    assert r_comm.status_code == 403

    r_hist = client.get(f"/api/v1/tickets/{ticket.id}/history", headers={"Authorization": f"Bearer {intruder_token}"})
    assert r_hist.status_code == 403


def test_ticket_history_recording_on_status_transitions(client: TestClient, db_session: Session):
    """Verify ticket status changes are recorded in ticket_history with actor, previous status, and new status."""
    cust_id, cust_token = create_user_token(db_session, name="Hist Cust", email="hist_c@example.com")
    agent_id, agent_token = create_user_token(db_session, name="Hist Agent", email="hist_ag@example.com", role=UserRole.AGENT)

    # 1. Create ticket -> initial history entry (None -> OPEN)
    res_create = client.post(
        "/api/v1/tickets",
        json={"title": "Status Test", "description": "Tracking transitions"},
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    ticket_id = res_create.json()["id"]

    # Assign ticket to agent
    ticket = db_session.get(Ticket, ticket_id)
    ticket.assigned_agent_id = agent_id
    db_session.commit()

    # 2. Agent transitions OPEN -> IN_PROGRESS
    res_trans1 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert res_trans1.status_code == 200

    # 3. Agent transitions IN_PROGRESS -> RESOLVED
    res_trans2 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert res_trans2.status_code == 200

    # 4. Retrieve history list
    res_history = client.get(
        f"/api/v1/tickets/{ticket_id}/history",
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert res_history.status_code == 200
    history_items = res_history.json()["items"]

    assert len(history_items) == 3
    # First entry: Initial creation
    assert history_items[0]["old_status"] is None
    assert history_items[0]["new_status"] == "open"
    assert history_items[0]["changed_by"] == cust_id

    # Second entry: open -> in_progress
    assert history_items[1]["old_status"] == "open"
    assert history_items[1]["new_status"] == "in_progress"
    assert history_items[1]["changed_by"] == agent_id

    # Third entry: in_progress -> resolved
    assert history_items[2]["old_status"] == "in_progress"
    assert history_items[2]["new_status"] == "resolved"
    assert history_items[2]["changed_by"] == agent_id


def test_atomic_transaction_rollback_on_update_failure():
    """Verify ticket updates and history records roll back atomically if a transaction failure occurs."""
    from tests.conftest import TestingSessionLocal
    session = TestingSessionLocal()
    cust_id = None
    agent = None
    ticket = None
    try:
        cust_id, _ = create_user_token(session, name="Atom Cust", email="atom_c@example.com")
        agent = user_service.create_user_with_role(
            session,
            name="Atom Agent",
            email="atom_ag@example.com",
            role=UserRole.AGENT,
            password="ValidPassword123!",
        )

        ticket = Ticket(
            customer_id=cust_id,
            assigned_agent_id=agent.id,
            title="Atomic Test Ticket",
            description="Desc",
            status=TicketStatus.OPEN,
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)

        ticket_id = ticket.id
        initial_status = ticket.status

        # Simulate an error during commit to test rollback atomicity
        from app.schemas.ticket import TicketUpdate
        update_data = TicketUpdate(status=TicketStatus.IN_PROGRESS)

        with patch.object(session, "commit", side_effect=RuntimeError("Database write failure")):
            with pytest.raises(RuntimeError):
                ticket_service.update_ticket(
                    session,
                    ticket=ticket,
                    current_user=agent,
                    data=update_data,
                )

        # Rollback should leave the ticket status unchanged and no history created
        fresh_ticket = session.get(Ticket, ticket_id)
        assert fresh_ticket is not None
        assert fresh_ticket.status == initial_status

        history_records = session.query(TicketHistory).filter(
            TicketHistory.ticket_id == ticket_id,
            TicketHistory.new_status == TicketStatus.IN_PROGRESS,
        ).all()
        assert len(history_records) == 0
    finally:
        if ticket and ticket.id:
            session.query(TicketHistory).filter(TicketHistory.ticket_id == ticket.id).delete()
            session.query(Ticket).filter(Ticket.id == ticket.id).delete()
        user_ids = [uid for uid in [cust_id, agent.id if agent else None] if uid]
        if user_ids:
            session.query(User).filter(User.id.in_(user_ids)).delete()
        session.commit()
        session.close()
