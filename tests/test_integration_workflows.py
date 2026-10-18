"""End-to-End integration tests for Customer, Agent, and Admin workflows,
error handling, malformed requests, and OpenAPI validation.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole, TicketStatus, TicketPriority
from app.models.ticket import Ticket
from app.services.user import user_service
from app.services.ticket import ticket_service
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


# =============================================================================
# WORKFLOW 1: CUSTOMER END-TO-END WORKFLOW
# =============================================================================

def test_customer_complete_lifecycle(client: TestClient):
    """E2E Workflow: Customer registers, logs in, creates ticket, views it, updates permitted fields,
    comments, and is prevented from privilege escalation or unauthorized actions.
    """
    # 1. Register customer
    reg_payload = {
        "name": "E2E Customer",
        "email": "e2e_cust@example.com",
        "password": "Password123!",
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    user_data = reg_res.json()
    assert user_data["role"] == "customer"
    assert "password" not in user_data
    assert "password_hash" not in user_data

    # 2. Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": reg_payload["email"], "password": reg_payload["password"]},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. View profile
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == reg_payload["email"]

    # 4. Create Ticket
    ticket_payload = {
        "title": "Payment gateway failure",
        "description": "Checkout button produces an error on credit card submission.",
        "priority": "high",
    }
    create_res = client.post("/api/v1/tickets", json=ticket_payload, headers=headers)
    assert create_res.status_code == 201
    ticket = create_res.json()
    ticket_id = ticket["id"]
    assert ticket["status"] == "open"
    assert ticket["customer_id"] == user_data["id"]

    # 5. List tickets (Customer sees own ticket)
    list_res = client.get("/api/v1/tickets", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1
    assert any(t["id"] == ticket_id for t in list_res.json()["items"])

    # 6. Retrieve single ticket
    get_res = client.get(f"/api/v1/tickets/{ticket_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["title"] == ticket_payload["title"]

    # 7. Update permitted fields (title, description)
    update_res = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"title": "Payment gateway failure (Stripe)", "description": "Updated error log."},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Payment gateway failure (Stripe)"

    # 8. Attempt forbidden updates (status, priority, assigned_agent)
    forbidden_update = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"status": "resolved"},
        headers=headers,
    )
    assert forbidden_update.status_code == 403

    # 9. Attempt forbidden ticket assignment
    forbidden_assign = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assigned_agent_id": 2},
        headers=headers,
    )
    assert forbidden_assign.status_code == 403

    # 10. Add Comment
    comment_res = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "I attached the transaction ID for reference."},
        headers=headers,
    )
    assert comment_res.status_code == 201
    assert comment_res.json()["author_id"] == user_data["id"]

    # 11. View Comments
    comments_list = client.get(f"/api/v1/tickets/{ticket_id}/comments", headers=headers)
    assert comments_list.status_code == 200
    assert len(comments_list.json()["items"]) == 1
    assert comments_list.json()["items"][0]["body"] == "I attached the transaction ID for reference."


# =============================================================================
# WORKFLOW 2: AGENT END-TO-END WORKFLOW
# =============================================================================

def test_agent_complete_lifecycle(client: TestClient, db_session: Session):
    """E2E Workflow: Agent logs in, receives assigned ticket, updates status, comments,
    and history records all transitions.
    """
    # Create users
    cust_id, _ = create_user_token(db_session, name="Workflow Customer", email="wf_cust@example.com")
    agent_id, agent_token = create_user_token(db_session, name="Workflow Agent", email="wf_agent@example.com", role=UserRole.AGENT)
    _, admin_token = create_user_token(db_session, name="Workflow Admin", email="wf_admin@example.com", role=UserRole.ADMIN)

    agent_headers = {"Authorization": f"Bearer {agent_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Customer creates ticket
    ticket = Ticket(customer_id=cust_id, title="Need support", description="Help needed")
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    ticket_id = ticket.id

    # 2. Agent cannot see ticket yet (unassigned)
    agent_list1 = client.get("/api/v1/tickets", headers=agent_headers)
    assert agent_list1.status_code == 200
    assert not any(t["id"] == ticket_id for t in agent_list1.json()["items"])

    # 3. Admin assigns ticket to Agent
    assign_res = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assigned_agent_id": agent_id},
        headers=admin_headers,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["assigned_agent_id"] == agent_id

    # 4. Agent now sees ticket in their assigned list
    agent_list2 = client.get("/api/v1/tickets", headers=agent_headers)
    assert agent_list2.status_code == 200
    assert any(t["id"] == ticket_id for t in agent_list2.json()["items"])

    # 5. Agent updates status: open -> in_progress
    prog_res = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"status": "in_progress"},
        headers=agent_headers,
    )
    assert prog_res.status_code == 200
    assert prog_res.json()["status"] == "in_progress"

    # 6. Agent posts comment
    comm_res = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "Investigating the server logs now."},
        headers=agent_headers,
    )
    assert comm_res.status_code == 201
    assert comm_res.json()["author_id"] == agent_id

    # 7. Agent updates status: in_progress -> resolved
    res_res = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"status": "resolved"},
        headers=agent_headers,
    )
    assert res_res.status_code == 200
    assert res_res.json()["status"] == "resolved"

    # 8. Check ticket history reflects transitions
    history_res = client.get(f"/api/v1/tickets/{ticket_id}/history", headers=agent_headers)
    assert history_res.status_code == 200
    items = history_res.json()["items"]
    assert len(items) >= 2
    # Verify the transitions
    transitions = [(h["old_status"], h["new_status"]) for h in items]
    assert ("open", "in_progress") in transitions
    assert ("in_progress", "resolved") in transitions

    # 9. Agent cannot assign tickets to others
    reassign_res = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assigned_agent_id": None},
        headers=agent_headers,
    )
    assert reassign_res.status_code == 403


# =============================================================================
# WORKFLOW 3: ADMIN END-TO-END WORKFLOW & ANALYTICS
# =============================================================================

def test_admin_complete_lifecycle(client: TestClient, db_session: Session):
    """E2E Workflow: Admin monitors all tickets, filters, assigns, comments, and views analytics."""
    cust_id, _ = create_user_token(db_session, name="Adm Customer", email="adm_c@example.com")
    agent_id, _ = create_user_token(db_session, name="Adm Agent", email="adm_a@example.com", role=UserRole.AGENT)
    _, admin_token = create_user_token(db_session, name="Super Admin", email="super_admin@example.com", role=UserRole.ADMIN)

    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create several tickets
    t1 = Ticket(customer_id=cust_id, assigned_agent_id=agent_id, title="Ticket 1", description="D1", status=TicketStatus.OPEN, priority=TicketPriority.URGENT)
    t2 = Ticket(customer_id=cust_id, assigned_agent_id=agent_id, title="Ticket 2", description="D2", status=TicketStatus.IN_PROGRESS, priority=TicketPriority.LOW)
    t3 = Ticket(customer_id=cust_id, assigned_agent_id=None, title="Ticket 3", description="D3", status=TicketStatus.RESOLVED, priority=TicketPriority.MEDIUM)
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # 1. Admin lists all tickets across system
    all_tickets = client.get("/api/v1/tickets", headers=admin_headers)
    assert all_tickets.status_code == 200
    assert all_tickets.json()["total"] >= 3

    # 2. Filter by status and priority
    filtered = client.get("/api/v1/tickets?status=open&priority=urgent", headers=admin_headers)
    assert filtered.status_code == 200
    assert all(t["status"] == "open" and t["priority"] == "urgent" for t in filtered.json()["items"])

    # 3. Filter by assigned agent
    agent_filtered = client.get(f"/api/v1/tickets?assigned_agent_id={agent_id}", headers=admin_headers)
    assert agent_filtered.status_code == 200
    assert all(t["assigned_agent_id"] == agent_id for t in agent_filtered.json()["items"])

    # 4. Analytics: status counts
    stats = client.get("/api/v1/analytics/tickets/status-counts", headers=admin_headers)
    assert stats.status_code == 200
    counts = stats.json()
    assert counts["open"] >= 1
    assert counts["in_progress"] >= 1
    assert counts["resolved"] >= 1
    assert "closed" in counts  # Zero status present

    # 5. Analytics: agent workload ranking
    ranking = client.get("/api/v1/analytics/agents/unresolved", headers=admin_headers)
    assert ranking.status_code == 200
    agent_rank = next(a for a in ranking.json() if a["agent_id"] == agent_id)
    assert agent_rank["unresolved_count"] == 2  # t1 (open) + t2 (in_progress)


# =============================================================================
# WORKFLOW 4: MALFORMED REQUESTS & ERROR HANDLING
# =============================================================================

def test_malformed_requests_and_validation_errors(client: TestClient, db_session: Session):
    """Test 400, 404, 409, 422 error codes, malformed payloads, and nonexistent resources."""
    cust_id, cust_token = create_user_token(db_session, name="Err Cust", email="err_cust@example.com")
    _, admin_token = create_user_token(db_session, name="Err Admin", email="err_admin@example.com", role=UserRole.ADMIN)

    cust_headers = {"Authorization": f"Bearer {cust_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Nonexistent ticket returns 404
    assert client.get("/api/v1/tickets/999999", headers=admin_headers).status_code == 404
    assert client.get("/api/v1/tickets/999999/comments", headers=admin_headers).status_code == 404
    assert client.get("/api/v1/tickets/999999/history", headers=admin_headers).status_code == 404
    assert client.patch("/api/v1/tickets/999999/assign", json={"assigned_agent_id": None}, headers=admin_headers).status_code == 404

    # 2. Duplicate registration returns 409 Conflict
    dup_res = client.post(
        "/api/v1/auth/register",
        json={"name": "Dup", "email": "err_cust@example.com", "password": "Password123!"},
    )
    assert dup_res.status_code == 409
    assert "already registered" in dup_res.json()["detail"]

    # 3. Invalid status value returns 422 Unprocessable Entity
    ticket = Ticket(customer_id=cust_id, title="Err Ticket", description="Desc")
    db_session.add(ticket)
    db_session.commit()

    invalid_status = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"status": "invalid_banana_status"},
        headers=admin_headers,
    )
    assert invalid_status.status_code == 422

    # 4. Invalid priority value returns 422
    invalid_priority = client.post(
        "/api/v1/tickets",
        json={"title": "T", "description": "D", "priority": "ultra_mega_high"},
        headers=cust_headers,
    )
    assert invalid_priority.status_code == 422

    # 5. Empty or whitespace-only comment body returns 422
    whitespace_comm = client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        json={"body": "     "},
        headers=cust_headers,
    )
    assert whitespace_comm.status_code == 422

    # 6. Assigning ticket to a non-existent user returns 404
    no_user_assign = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": 888888},
        headers=admin_headers,
    )
    assert no_user_assign.status_code == 404

    # 7. Assigning ticket to a user who is a customer (not an agent) returns 400
    cust_assign = client.patch(
        f"/api/v1/tickets/{ticket.id}/assign",
        json={"assigned_agent_id": cust_id},
        headers=admin_headers,
    )
    assert cust_assign.status_code == 400
    assert "agent" in cust_assign.json()["detail"].lower()

    # 8. Pagination invalid values (page <= 0, page_size > 100) return 422
    assert client.get("/api/v1/tickets?page=0", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/tickets?page_size=200", headers=admin_headers).status_code == 422


# =============================================================================
# WORKFLOW 5: OPENAPI, SWAGGER UI & ERROR SANITIZATION
# =============================================================================

def test_openapi_and_docs_availability(client: TestClient):
    """Verify OpenAPI 3.1.0 JSON and Swagger UI endpoints are operational."""
    # Check OpenAPI JSON at /openapi.json
    res_openapi = client.get("/openapi.json")
    assert res_openapi.status_code == 200
    openapi_doc = res_openapi.json()
    assert openapi_doc["openapi"].startswith("3.")
    assert "paths" in openapi_doc

    # Check Swagger UI at /docs
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
    assert "swagger-ui" in res_docs.text.lower()

    # Check compatibility redirects
    res_v1_docs = client.get("/api/v1/docs", follow_redirects=True)
    assert res_v1_docs.status_code == 200

    res_v1_openapi = client.get("/api/v1/openapi.json", follow_redirects=True)
    assert res_v1_openapi.status_code == 200


def test_unhandled_error_response_sanitization():
    """Verify unexpected internal exceptions do not leak stack traces, SQL, or secrets."""
    from app.main import app
    from app.api.deps import require_admin
    from app.models.user import User

    test_client = TestClient(app, raise_server_exceptions=False)
    mock_admin = User(id=1, name="Mock Admin", email="m@ex.com", role=UserRole.ADMIN, password_hash="hash")
    app.dependency_overrides[require_admin] = lambda: mock_admin

    try:
        with patch("app.services.analytics.AnalyticsService.get_status_counts", side_effect=RuntimeError("SecretDatabaseException: SELECT * FROM secrets_tbl WHERE pass='123'")):
            response = test_client.get("/api/v1/analytics/tickets/status-counts")
            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            # Ensure sensitive information is never returned in client response
            assert "SecretDatabaseException" not in data["detail"]
            assert "SELECT" not in data["detail"]
            assert "secrets_tbl" not in data["detail"]
            assert "Traceback" not in data["detail"]
    finally:
        app.dependency_overrides.pop(require_admin, None)
