"""Tests for core ticket management APIs, RBAC, ownership, filtering, pagination, and assignment."""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole, TicketStatus, TicketPriority
from app.models.user import User
from app.models.ticket import Ticket
from app.models.ticket_history import TicketHistory
from app.services.user import user_service
from app.services.ticket import ticket_service
from app.core.security import create_access_token


def create_test_user(
    db_session: Session,
    *,
    name: str,
    email: str,
    role: UserRole = UserRole.CUSTOMER,
    password: str = "SecurePass123!",
) -> tuple[User, str]:
    """Helper to create user and return user instance along with JWT access token."""
    user = user_service.create_user_with_role(
        db_session,
        name=name,
        email=email,
        password=password,
        role=role,
    )
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(subject=user.id, extra_claims={"email": user.email, "role": role_str})
    return user, token


def test_customer_create_ticket_success(client: TestClient, db_session: Session):
    """Verify customer can create a ticket with valid inputs and is set as owner."""
    customer, token = create_test_user(db_session, name="Ticket Creator", email="creator@example.com")

    payload = {
        "title": "Cannot access dashboard",
        "description": "Getting a 500 error when logging into analytics.",
        "priority": "high",
    }
    response = client.post(
        "/api/v1/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["priority"] == "high"
    assert data["status"] == "open"
    assert data["customer_id"] == customer.id
    assert data["assigned_agent_id"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_customer_create_ticket_cannot_assign_agent(client: TestClient, db_session: Session):
    """Verify customer cannot self-assign an agent during ticket creation."""
    customer, token = create_test_user(db_session, name="Sneaky Cust", email="sneaky@example.com")
    agent, _ = create_test_user(db_session, name="Agent One", email="agent1@example.com", role=UserRole.AGENT)

    payload = {
        "title": "Issue with assignment",
        "description": "Attempting to assign on creation",
        "assigned_agent_id": agent.id,  # Should be ignored on creation
    }
    response = client.post(
        "/api/v1/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["assigned_agent_id"] is None  # Always starts unassigned


def test_create_ticket_invalid_input_validation(client: TestClient, db_session: Session):
    """Verify invalid inputs return 422 Unprocessable Entity."""
    _, token = create_test_user(db_session, name="Validation User", email="val_user@example.com")

    # Empty title
    r1 = client.post(
        "/api/v1/tickets",
        json={"title": "", "description": "Valid description"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 422

    # Invalid priority
    r2 = client.post(
        "/api/v1/tickets",
        json={"title": "Valid title", "description": "Valid description", "priority": "super_urgent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 422


def test_unauthenticated_ticket_endpoints_return_401(client: TestClient):
    """Verify ticket endpoints reject requests without valid authentication."""
    assert client.post("/api/v1/tickets", json={"title": "T", "description": "D"}).status_code == 401
    assert client.get("/api/v1/tickets").status_code == 401
    assert client.get("/api/v1/tickets/1").status_code == 401
    assert client.patch("/api/v1/tickets/1", json={"title": "Updated"}).status_code == 401
    assert client.patch("/api/v1/tickets/1/assign", json={"assigned_agent_id": 1}).status_code == 401


def test_customer_lists_only_own_tickets(client: TestClient, db_session: Session):
    """Verify customers can only view their own tickets, not other customers'."""
    cust_a, token_a = create_test_user(db_session, name="Cust A", email="cust_a@example.com")
    cust_b, token_b = create_test_user(db_session, name="Cust B", email="cust_b@example.com")

    # Create ticket for Cust A
    client.post(
        "/api/v1/tickets",
        json={"title": "Ticket A", "description": "Description A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Create ticket for Cust B
    client.post(
        "/api/v1/tickets",
        json={"title": "Ticket B", "description": "Description B"},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # Cust A list
    res_a = client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    items_a = res_a.json()["items"]
    assert len(items_a) == 1
    assert items_a[0]["title"] == "Ticket A"

    # Cust B list
    res_b = client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    items_b = res_b.json()["items"]
    assert len(items_b) == 1
    assert items_b[0]["title"] == "Ticket B"


def test_agent_lists_only_assigned_tickets(client: TestClient, db_session: Session):
    """Verify support agents only see tickets assigned to them."""
    cust, _ = create_test_user(db_session, name="Shared Cust", email="shared@example.com")
    agent_1, token_1 = create_test_user(db_session, name="Agent 1", email="agent_1@example.com", role=UserRole.AGENT)
    agent_2, token_2 = create_test_user(db_session, name="Agent 2", email="agent_2@example.com", role=UserRole.AGENT)

    # Create ticket assigned to Agent 1
    t1 = Ticket(
        customer_id=cust.id,
        assigned_agent_id=agent_1.id,
        title="Agent 1 Ticket",
        description="Assigned to Agent 1",
    )
    # Create ticket assigned to Agent 2
    t2 = Ticket(
        customer_id=cust.id,
        assigned_agent_id=agent_2.id,
        title="Agent 2 Ticket",
        description="Assigned to Agent 2",
    )
    # Unassigned ticket
    t3 = Ticket(
        customer_id=cust.id,
        assigned_agent_id=None,
        title="Unassigned Ticket",
        description="No agent assigned",
    )
    db_session.add_all([t1, t2, t3])
    db_session.flush()

    res_1 = client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {token_1}"})
    assert res_1.status_code == 200
    items_1 = res_1.json()["items"]
    assert len(items_1) == 1
    assert items_1[0]["title"] == "Agent 1 Ticket"

    res_2 = client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {token_2}"})
    assert res_2.status_code == 200
    items_2 = res_2.json()["items"]
    assert len(items_2) == 1
    assert items_2[0]["title"] == "Agent 2 Ticket"


def test_admin_lists_all_tickets(client: TestClient, db_session: Session):
    """Verify administrator can view all tickets across all customers and agents."""
    cust, _ = create_test_user(db_session, name="All Cust", email="all_cust@example.com")
    agent, _ = create_test_user(db_session, name="All Agent", email="all_agent@example.com", role=UserRole.AGENT)
    _, token_admin = create_test_user(db_session, name="Admin All", email="admin_all@example.com", role=UserRole.ADMIN)

    t1 = Ticket(customer_id=cust.id, assigned_agent_id=agent.id, title="Ticket 1", description="Desc 1")
    t2 = Ticket(customer_id=cust.id, assigned_agent_id=None, title="Ticket 2", description="Desc 2")
    db_session.add_all([t1, t2])
    db_session.flush()

    res = client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {token_admin}"})
    assert res.status_code == 200
    assert res.json()["total"] >= 2


def test_customer_filtering_restrictions_enforced(client: TestClient, db_session: Session):
    """Verify customer cannot filter by other customer_id or assigned_agent_id."""
    _, token_cust = create_test_user(db_session, name="Filter Cust", email="filter_cust@example.com")

    # Attempt to filter by another customer ID -> 403 Forbidden
    r1 = client.get("/api/v1/tickets?customer_id=999", headers={"Authorization": f"Bearer {token_cust}"})
    assert r1.status_code == 403
    assert "cannot filter by other customers" in r1.json()["detail"].lower()

    # Attempt to filter by assigned agent ID -> 403 Forbidden
    r2 = client.get("/api/v1/tickets?assigned_agent_id=1", headers={"Authorization": f"Bearer {token_cust}"})
    assert r2.status_code == 403
    assert "not authorized to filter by assigned agent" in r2.json()["detail"].lower()


def test_filtering_by_status_and_priority(client: TestClient, db_session: Session):
    """Verify filtering by status and priority returns matching tickets."""
    cust, _ = create_test_user(db_session, name="Filter Status Cust", email="f_status@example.com")
    _, token_admin = create_test_user(db_session, name="Filter Admin", email="f_admin@example.com", role=UserRole.ADMIN)

    t_open_low = Ticket(customer_id=cust.id, title="Open Low", description="Desc", status=TicketStatus.OPEN, priority=TicketPriority.LOW)
    t_resolved_high = Ticket(customer_id=cust.id, title="Resolved High", description="Desc", status=TicketStatus.RESOLVED, priority=TicketPriority.HIGH)
    db_session.add_all([t_open_low, t_resolved_high])
    db_session.flush()

    # Filter by status=resolved
    r_status = client.get("/api/v1/tickets?status=resolved", headers={"Authorization": f"Bearer {token_admin}"})
    assert r_status.status_code == 200
    for item in r_status.json()["items"]:
        assert item["status"] == "resolved"

    # Filter by priority=high
    r_priority = client.get("/api/v1/tickets?priority=high", headers={"Authorization": f"Bearer {token_admin}"})
    assert r_priority.status_code == 200
    for item in r_priority.json()["items"]:
        assert item["priority"] == "high"


def test_filtering_by_date_range(client: TestClient, db_session: Session):
    """Verify filtering tickets by created_after and created_before date range."""
    cust, _ = create_test_user(db_session, name="Date Cust", email="date_cust@example.com")
    _, token_admin = create_test_user(db_session, name="Date Admin", email="date_admin@example.com", role=UserRole.ADMIN)

    now = datetime.now(timezone.utc)
    t_past = Ticket(
        customer_id=cust.id,
        title="Past Ticket",
        description="Created in past",
        created_at=now - timedelta(days=5),
    )
    t_recent = Ticket(
        customer_id=cust.id,
        title="Recent Ticket",
        description="Created recently",
        created_at=now,
    )
    db_session.add_all([t_past, t_recent])
    db_session.flush()

    # Filter for tickets created in the last 2 days
    after_iso = (now - timedelta(days=2)).isoformat()
    res = client.get(
        "/api/v1/tickets",
        params={"created_after": after_iso},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res.status_code == 200
    titles = [item["title"] for item in res.json()["items"]]
    assert "Recent Ticket" in titles
    assert "Past Ticket" not in titles


def test_pagination_and_validation(client: TestClient, db_session: Session):
    """Verify pagination calculation and page parameter validation."""
    cust, _ = create_test_user(db_session, name="Pag Cust", email="pag_cust@example.com")
    _, token_admin = create_test_user(db_session, name="Pag Admin", email="pag_admin@example.com", role=UserRole.ADMIN)

    # Insert 15 tickets
    for i in range(15):
        db_session.add(Ticket(customer_id=cust.id, title=f"Paginated {i}", description=f"Desc {i}"))
    db_session.flush()

    # Request page 1 with page_size=5
    res = client.get("/api/v1/tickets?page=1&page_size=5", headers={"Authorization": f"Bearer {token_admin}"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 5
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert data["total"] >= 15
    assert data["pages"] >= 3

    # Invalid page (< 1) returns 422
    assert client.get("/api/v1/tickets?page=0", headers={"Authorization": f"Bearer {token_admin}"}).status_code == 422
    # Invalid page_size (> 100) returns 422
    assert client.get("/api/v1/tickets?page_size=101", headers={"Authorization": f"Bearer {token_admin}"}).status_code == 422


def test_get_single_ticket_access_control(client: TestClient, db_session: Session):
    """Verify single ticket retrieval access rules for Customer, Agent, and Admin."""
    cust_owner, token_owner = create_test_user(db_session, name="Ticket Owner", email="owner@example.com")
    cust_other, token_other = create_test_user(db_session, name="Other Cust", email="other@example.com")
    agent_assigned, token_agent = create_test_user(db_session, name="Assigned Agent", email="assigned_ag@example.com", role=UserRole.AGENT)
    _, token_unassigned_agent = create_test_user(db_session, name="Unassigned Agent", email="unassigned_ag@example.com", role=UserRole.AGENT)
    _, token_admin = create_test_user(db_session, name="Super Admin", email="super_admin@example.com", role=UserRole.ADMIN)

    ticket = Ticket(
        customer_id=cust_owner.id,
        assigned_agent_id=agent_assigned.id,
        title="Access Control Test Ticket",
        description="Detailed description",
    )
    db_session.add(ticket)
    db_session.flush()

    # 1. Customer owner can view -> 200
    r_owner = client.get(f"/api/v1/tickets/{ticket.id}", headers={"Authorization": f"Bearer {token_owner}"})
    assert r_owner.status_code == 200

    # 2. Other customer is forbidden -> 403
    r_other = client.get(f"/api/v1/tickets/{ticket.id}", headers={"Authorization": f"Bearer {token_other}"})
    assert r_other.status_code == 403

    # 3. Assigned agent can view -> 200
    r_agent = client.get(f"/api/v1/tickets/{ticket.id}", headers={"Authorization": f"Bearer {token_agent}"})
    assert r_agent.status_code == 200

    # 4. Unassigned agent is forbidden -> 403
    r_unassigned_agent = client.get(f"/api/v1/tickets/{ticket.id}", headers={"Authorization": f"Bearer {token_unassigned_agent}"})
    assert r_unassigned_agent.status_code == 403

    # 5. Admin can view -> 200
    r_admin = client.get(f"/api/v1/tickets/{ticket.id}", headers={"Authorization": f"Bearer {token_admin}"})
    assert r_admin.status_code == 200

    # 6. Non-existent ticket -> 404
    r_not_found = client.get("/api/v1/tickets/999999", headers={"Authorization": f"Bearer {token_admin}"})
    assert r_not_found.status_code == 404


def test_customer_update_ticket_permitted_and_forbidden_fields(client: TestClient, db_session: Session):
    """Verify customers can update title and description, but not status or priority."""
    customer, token = create_test_user(db_session, name="Updater Cust", email="updater@example.com")
    ticket = Ticket(
        customer_id=customer.id,
        title="Original Title",
        description="Original Description",
        priority=TicketPriority.MEDIUM,
        status=TicketStatus.OPEN,
    )
    db_session.add(ticket)
    db_session.flush()

    # 1. Customer updates title and description -> 200 OK
    res_ok = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"title": "Updated Title", "description": "Updated Description"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["title"] == "Updated Title"
    assert res_ok.json()["description"] == "Updated Description"

    # 2. Customer attempts to change status -> 403 Forbidden
    res_status = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_status.status_code == 403
    assert "not permitted to change ticket status" in res_status.json()["detail"].lower()

    # 3. Customer attempts to change priority -> 403 Forbidden
    res_priority = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"priority": "urgent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_priority.status_code == 403


def test_agent_update_assigned_ticket_status_and_history(client: TestClient, db_session: Session):
    """Verify agent can update status of assigned ticket and status transition is recorded in history."""
    cust, _ = create_test_user(db_session, name="Agent Update Cust", email="ag_up_c@example.com")
    agent, token_agent = create_test_user(db_session, name="Managing Agent", email="m_ag@example.com", role=UserRole.AGENT)

    ticket = Ticket(
        customer_id=cust.id,
        assigned_agent_id=agent.id,
        title="Agent Ticket",
        description="Needs triage",
        status=TicketStatus.OPEN,
    )
    db_session.add(ticket)
    db_session.flush()

    # Agent updates status to in_progress
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token_agent}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"

    # Verify history entry created
    history = db_session.query(TicketHistory).filter(TicketHistory.ticket_id == ticket.id).first()
    assert history is not None
    assert history.old_status == TicketStatus.OPEN
    assert history.new_status == TicketStatus.IN_PROGRESS
    assert history.changed_by == agent.id


def test_agent_cannot_update_unassigned_ticket(client: TestClient, db_session: Session):
    """Verify agent cannot update a ticket not assigned to them."""
    cust, _ = create_test_user(db_session, name="Cust T", email="cust_t@example.com")
    agent_1, _ = create_test_user(db_session, name="Agent A1", email="a1@example.com", role=UserRole.AGENT)
    _, token_agent_2 = create_test_user(db_session, name="Agent A2", email="a2@example.com", role=UserRole.AGENT)

    ticket = Ticket(customer_id=cust.id, assigned_agent_id=agent_1.id, title="Title", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    res = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token_agent_2}"},
    )
    assert res.status_code == 403


def test_admin_assign_ticket_to_valid_agent(client: TestClient, db_session: Session):
    """Verify administrator can assign ticket to a user with the agent role."""
    cust, _ = create_test_user(db_session, name="Assign Cust", email="assign_c@example.com")
    agent, _ = create_test_user(db_session, name="Target Agent", email="target_ag@example.com", role=UserRole.AGENT)
    _, token_admin = create_test_user(db_session, name="Assign Admin", email="assign_ad@example.com", role=UserRole.ADMIN)

    ticket = Ticket(customer_id=cust.id, title="Unassigned", description="Desc", assigned_agent_id=None)
    db_session.add(ticket)
    db_session.flush()

    # Assign to agent
    res = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": agent.id},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res.status_code == 200
    assert res.json()["assigned_agent_id"] == agent.id

    # Unassign ticket (set to null)
    res_unassign = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": None},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_unassign.status_code == 200
    assert res_unassign.json()["assigned_agent_id"] is None


def test_admin_assign_ticket_to_customer_rejected(client: TestClient, db_session: Session):
    """Verify assigning a ticket to a user with customer role returns 400 Bad Request."""
    cust1, _ = create_test_user(db_session, name="Cust 1", email="c1@example.com")
    cust2, _ = create_test_user(db_session, name="Cust 2", email="c2@example.com")
    _, token_admin = create_test_user(db_session, name="Admin X", email="admin_x@example.com", role=UserRole.ADMIN)

    ticket = Ticket(customer_id=cust1.id, title="Title", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    res = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": cust2.id},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res.status_code == 400
    assert "only be assigned to users with the 'agent' role" in res.json()["detail"].lower()


def test_admin_assign_ticket_to_nonexistent_agent_returns_404(client: TestClient, db_session: Session):
    """Verify assigning a ticket to non-existent agent returns 404 Not Found."""
    cust, _ = create_test_user(db_session, name="Cust Y", email="c_y@example.com")
    _, token_admin = create_test_user(db_session, name="Admin Y", email="admin_y@example.com", role=UserRole.ADMIN)

    ticket = Ticket(customer_id=cust.id, title="Title", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    res = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": 999999},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res.status_code == 404


def test_non_admin_cannot_assign_ticket(client: TestClient, db_session: Session):
    """Verify customers and agents are forbidden from calling the assign endpoint."""
    cust, token_cust = create_test_user(db_session, name="Cust Z", email="cz@example.com")
    agent, token_agent = create_test_user(db_session, name="Agent Z", email="az@example.com", role=UserRole.AGENT)

    ticket = Ticket(customer_id=cust.id, title="Title", description="Desc")
    db_session.add(ticket)
    db_session.flush()

    # Customer attempt -> 403 Forbidden
    res_c = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": agent.id},
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert res_c.status_code == 403

    # Agent attempt -> 403 Forbidden
    res_a = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": agent.id},
        headers={"Authorization": f"Bearer {token_agent}"},
    )
    assert res_a.status_code == 403


def test_root_ticket_alias_endpoints_work(client: TestClient, db_session: Session):
    """Verify root alias /tickets works identically to /api/v1/tickets."""
    customer, token = create_test_user(db_session, name="Root Alias Cust", email="root_alias@example.com")

    # POST /tickets
    res_create = client.post(
        "/tickets",
        json={"title": "Root Alias Title", "description": "Root alias desc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_create.status_code == 201
    ticket_id = res_create.json()["id"]

    # GET /tickets
    res_list = client.get("/tickets", headers={"Authorization": f"Bearer {token}"})
    assert res_list.status_code == 200
    assert len(res_list.json()["items"]) >= 1

    # GET /tickets/{id}
    res_get = client.get(f"/tickets/{ticket_id}", headers={"Authorization": f"Bearer {token}"})
    assert res_get.status_code == 200
    assert res_get.json()["id"] == ticket_id
