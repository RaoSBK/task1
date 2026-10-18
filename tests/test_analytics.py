"""Tests for ticket analytics, status counting, and agent unresolved workload reporting."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import UserRole, TicketStatus, TicketPriority
from app.models.ticket import Ticket
from app.services.user import user_service
from app.services.analytics import analytics_service
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


def test_unauthenticated_analytics_endpoints_return_401(client: TestClient):
    """Verify that unauthenticated requests to analytics endpoints return 401."""
    # Test versioned endpoints
    res1 = client.get("/api/v1/analytics/tickets/status-counts")
    assert res1.status_code == 401

    res2 = client.get("/api/v1/analytics/agents/unresolved")
    assert res2.status_code == 401

    # Test root alias endpoints
    res3 = client.get("/analytics/tickets/status-counts")
    assert res3.status_code == 401

    res4 = client.get("/analytics/agents/unresolved")
    assert res4.status_code == 401


def test_non_admin_cannot_access_analytics(client: TestClient, db_session: Session):
    """Verify customers and agents receive 403 Forbidden on analytics endpoints."""
    _, cust_token = create_user_token(db_session, name="Analyst Customer", email="cust_ana@example.com", role=UserRole.CUSTOMER)
    _, agent_token = create_user_token(db_session, name="Analyst Agent", email="agent_ana@example.com", role=UserRole.AGENT)

    # Customer forbidden
    res_cust1 = client.get("/api/v1/analytics/tickets/status-counts", headers={"Authorization": f"Bearer {cust_token}"})
    assert res_cust1.status_code == 403

    res_cust2 = client.get("/api/v1/analytics/agents/unresolved", headers={"Authorization": f"Bearer {cust_token}"})
    assert res_cust2.status_code == 403

    # Agent forbidden
    res_agent1 = client.get("/api/v1/analytics/tickets/status-counts", headers={"Authorization": f"Bearer {agent_token}"})
    assert res_agent1.status_code == 403

    res_agent2 = client.get("/api/v1/analytics/agents/unresolved", headers={"Authorization": f"Bearer {agent_token}"})
    assert res_agent2.status_code == 403


def test_status_counts_empty_database(client: TestClient, db_session: Session):
    """Verify status counts report all supported statuses as 0 when database has no tickets."""
    _, admin_token = create_user_token(db_session, name="Admin Empty", email="admin_empty@example.com", role=UserRole.ADMIN)

    response = client.get("/api/v1/analytics/tickets/status-counts", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()

    assert data["open"] == 0
    assert data["in_progress"] == 0
    assert data["resolved"] == 0
    assert data["closed"] == 0
    assert data["total"] == 0

    assert data["counts"]["open"] == 0
    assert data["counts"]["in_progress"] == 0
    assert data["counts"]["resolved"] == 0
    assert data["counts"]["closed"] == 0


def test_status_counts_mixed_statuses_and_zero_counts(client: TestClient, db_session: Session):
    """Verify status counts accurately count tickets and report statuses with zero tickets."""
    cust_id, _ = create_user_token(db_session, name="Ticket Owner", email="owner_mix@example.com")
    _, admin_token = create_user_token(db_session, name="Admin Mix", email="admin_mix@example.com", role=UserRole.ADMIN)

    # Create 3 open, 2 in_progress, 1 resolved, 0 closed
    tickets = [
        Ticket(customer_id=cust_id, title="Open 1", description="D", status=TicketStatus.OPEN),
        Ticket(customer_id=cust_id, title="Open 2", description="D", status=TicketStatus.OPEN),
        Ticket(customer_id=cust_id, title="Open 3", description="D", status=TicketStatus.OPEN),
        Ticket(customer_id=cust_id, title="Prog 1", description="D", status=TicketStatus.IN_PROGRESS),
        Ticket(customer_id=cust_id, title="Prog 2", description="D", status=TicketStatus.IN_PROGRESS),
        Ticket(customer_id=cust_id, title="Res 1", description="D", status=TicketStatus.RESOLVED),
    ]
    db_session.add_all(tickets)
    db_session.commit()

    response = client.get("/analytics/tickets/status-counts", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()

    assert data["open"] == 3
    assert data["in_progress"] == 2
    assert data["resolved"] == 1
    assert data["closed"] == 0  # Zero count explicitly reported
    assert data["total"] == 6

    # Test dictionary representations
    assert data["counts"]["open"] == 3
    assert data["counts"]["in_progress"] == 2
    assert data["counts"]["resolved"] == 1
    assert data["counts"]["closed"] == 0


def test_agents_unresolved_empty_database(client: TestClient, db_session: Session):
    """Verify agent unresolved ranking handles empty database gracefully."""
    _, admin_token = create_user_token(db_session, name="Admin No Agents", email="admin_noag@example.com", role=UserRole.ADMIN)

    response = client.get("/api/v1/analytics/agents/unresolved", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_agents_unresolved_zero_ticket_agents_included(client: TestClient, db_session: Session):
    """Verify agents with zero tickets or only resolved/closed tickets are included via LEFT JOIN."""
    agent1_id, _ = create_user_token(db_session, name="Zero Agent A", email="zero_a@example.com", role=UserRole.AGENT)
    agent2_id, _ = create_user_token(db_session, name="Zero Agent B", email="zero_b@example.com", role=UserRole.AGENT)
    cust_id, _ = create_user_token(db_session, name="Customer Zero", email="cust_zero@example.com", role=UserRole.CUSTOMER)
    _, admin_token = create_user_token(db_session, name="Admin Zero", email="admin_zero@example.com", role=UserRole.ADMIN)

    # Assign agent2 only resolved and closed tickets (unresolved should still be 0)
    t1 = Ticket(customer_id=cust_id, assigned_agent_id=agent2_id, title="Resolved T", description="D", status=TicketStatus.RESOLVED)
    t2 = Ticket(customer_id=cust_id, assigned_agent_id=agent2_id, title="Closed T", description="D", status=TicketStatus.CLOSED)
    db_session.add_all([t1, t2])
    db_session.commit()

    response = client.get("/analytics/agents/unresolved", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()

    # Both agents must be present in the report
    agent_ids = [item["agent_id"] for item in data]
    assert agent1_id in agent_ids
    assert agent2_id in agent_ids

    agent1_data = next(a for a in data if a["agent_id"] == agent1_id)
    assert agent1_data["unresolved_count"] == 0
    assert agent1_data["open_count"] == 0
    assert agent1_data["in_progress_count"] == 0

    agent2_data = next(a for a in data if a["agent_id"] == agent2_id)
    assert agent2_data["unresolved_count"] == 0
    assert agent2_data["open_count"] == 0
    assert agent2_data["in_progress_count"] == 0


def test_agents_unresolved_mixed_statuses_and_ranking_order(client: TestClient, db_session: Session):
    """Verify agents are correctly ranked by unresolved count descending with mixed statuses."""
    cust_id, _ = create_user_token(db_session, name="Customer Mixed", email="cust_mix_rank@example.com", role=UserRole.CUSTOMER)
    _, admin_token = create_user_token(db_session, name="Admin Rank", email="admin_rank@example.com", role=UserRole.ADMIN)

    # Agent Alpha: 3 unresolved (1 open, 2 in_progress) + 1 resolved
    alpha_id, _ = create_user_token(db_session, name="Agent Alpha", email="alpha@example.com", role=UserRole.AGENT)
    # Agent Beta: 1 unresolved (1 open) + 2 closed
    beta_id, _ = create_user_token(db_session, name="Agent Beta", email="beta@example.com", role=UserRole.AGENT)
    # Agent Charlie: 0 unresolved (only resolved)
    charlie_id, _ = create_user_token(db_session, name="Agent Charlie", email="charlie@example.com", role=UserRole.AGENT)

    tickets = [
        # Alpha tickets
        Ticket(customer_id=cust_id, assigned_agent_id=alpha_id, title="A1", description="D", status=TicketStatus.OPEN),
        Ticket(customer_id=cust_id, assigned_agent_id=alpha_id, title="A2", description="D", status=TicketStatus.IN_PROGRESS),
        Ticket(customer_id=cust_id, assigned_agent_id=alpha_id, title="A3", description="D", status=TicketStatus.IN_PROGRESS),
        Ticket(customer_id=cust_id, assigned_agent_id=alpha_id, title="A4", description="D", status=TicketStatus.RESOLVED),
        # Beta tickets
        Ticket(customer_id=cust_id, assigned_agent_id=beta_id, title="B1", description="D", status=TicketStatus.OPEN),
        Ticket(customer_id=cust_id, assigned_agent_id=beta_id, title="B2", description="D", status=TicketStatus.CLOSED),
        Ticket(customer_id=cust_id, assigned_agent_id=beta_id, title="B3", description="D", status=TicketStatus.CLOSED),
        # Charlie tickets
        Ticket(customer_id=cust_id, assigned_agent_id=charlie_id, title="C1", description="D", status=TicketStatus.RESOLVED),
    ]
    db_session.add_all(tickets)
    db_session.commit()

    response = client.get("/api/v1/analytics/agents/unresolved", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()

    # Filter to only the 3 agents created in this test
    ranked_test_agents = [item for item in data if item["agent_id"] in (alpha_id, beta_id, charlie_id)]
    assert len(ranked_test_agents) == 3

    # Rank 1: Alpha (3 unresolved)
    assert ranked_test_agents[0]["agent_id"] == alpha_id
    assert ranked_test_agents[0]["unresolved_count"] == 3
    assert ranked_test_agents[0]["open_count"] == 1
    assert ranked_test_agents[0]["in_progress_count"] == 2

    # Rank 2: Beta (1 unresolved)
    assert ranked_test_agents[1]["agent_id"] == beta_id
    assert ranked_test_agents[1]["unresolved_count"] == 1
    assert ranked_test_agents[1]["open_count"] == 1
    assert ranked_test_agents[1]["in_progress_count"] == 0

    # Rank 3: Charlie (0 unresolved)
    assert ranked_test_agents[2]["agent_id"] == charlie_id
    assert ranked_test_agents[2]["unresolved_count"] == 0
    assert ranked_test_agents[2]["open_count"] == 0
    assert ranked_test_agents[2]["in_progress_count"] == 0


def test_agents_unresolved_deterministic_tie_breaker(client: TestClient, db_session: Session):
    """Verify agents with identical unresolved counts are sorted deterministically by name, then ID."""
    cust_id, _ = create_user_token(db_session, name="Customer Ties", email="cust_ties@example.com", role=UserRole.CUSTOMER)
    _, admin_token = create_user_token(db_session, name="Admin Ties", email="admin_ties@example.com", role=UserRole.ADMIN)

    # 3 agents created with names in non-alphabetical order, each having 1 open ticket
    zoe_id, _ = create_user_token(db_session, name="Zoe Agent", email="zoe@example.com", role=UserRole.AGENT)
    alice_id, _ = create_user_token(db_session, name="Alice Agent", email="alice@example.com", role=UserRole.AGENT)
    bob_id, _ = create_user_token(db_session, name="Bob Agent", email="bob@example.com", role=UserRole.AGENT)

    t1 = Ticket(customer_id=cust_id, assigned_agent_id=zoe_id, title="Z", description="D", status=TicketStatus.OPEN)
    t2 = Ticket(customer_id=cust_id, assigned_agent_id=alice_id, title="A", description="D", status=TicketStatus.OPEN)
    t3 = Ticket(customer_id=cust_id, assigned_agent_id=bob_id, title="B", description="D", status=TicketStatus.OPEN)
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    response = client.get("/api/v1/analytics/agents/unresolved", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()

    test_agent_ids = [item["agent_id"] for item in data if item["agent_id"] in (zoe_id, alice_id, bob_id)]
    # All have 1 unresolved ticket, so tie-breaker orders them: Alice, Bob, Zoe
    assert test_agent_ids == [alice_id, bob_id, zoe_id]


def test_sql_file_analytics_queries_match_service_output(db_session: Session):
    """Verify queries in sql/analytics.sql produce exact results against PostgreSQL."""
    cust_id, _ = create_user_token(db_session, name="SQL Cust", email="sql_cust@example.com", role=UserRole.CUSTOMER)
    agent_id, _ = create_user_token(db_session, name="SQL Agent", email="sql_agent@example.com", role=UserRole.AGENT)

    t1 = Ticket(customer_id=cust_id, assigned_agent_id=agent_id, title="SQL T1", description="D1", status=TicketStatus.OPEN)
    t2 = Ticket(customer_id=cust_id, assigned_agent_id=agent_id, title="SQL T2", description="D2", status=TicketStatus.IN_PROGRESS)
    db_session.add_all([t1, t2])
    db_session.commit()

    # Execute service methods
    service_counts = analytics_service.get_status_counts(db_session)
    service_ranking = analytics_service.get_unresolved_agents_ranking(db_session)

    # Execute raw SQL from sql/analytics.sql (Query 2 CTE)
    sql_status_query = text("""
        WITH supported_statuses AS (
            SELECT 'open'::varchar AS status
            UNION ALL SELECT 'in_progress'::varchar
            UNION ALL SELECT 'resolved'::varchar
            UNION ALL SELECT 'closed'::varchar
        )
        SELECT s.status, COUNT(t.id) AS ticket_count
        FROM supported_statuses s
        LEFT JOIN tickets t ON t.status = s.status
        GROUP BY s.status
        ORDER BY s.status ASC;
    """)
    sql_counts = dict(db_session.execute(sql_status_query).fetchall())

    assert sql_counts["open"] == service_counts.open
    assert sql_counts["in_progress"] == service_counts.in_progress
    assert sql_counts["resolved"] == service_counts.resolved
    assert sql_counts["closed"] == service_counts.closed

    # Execute raw SQL for Query 3
    sql_agent_query = text("""
        SELECT 
            u.id AS agent_id,
            u.name AS agent_name,
            u.email AS agent_email,
            COUNT(t.id) AS unresolved_count
        FROM users u
        LEFT JOIN tickets t 
            ON t.assigned_agent_id = u.id 
            AND t.status IN ('open', 'in_progress')
        WHERE u.role = 'agent'
        GROUP BY u.id, u.name, u.email
        ORDER BY unresolved_count DESC, u.name ASC, u.id ASC;
    """)
    sql_ranking = db_session.execute(sql_agent_query).fetchall()

    agent_row = next(r for r in sql_ranking if r.agent_id == agent_id)
    service_row = next(r for r in service_ranking if r.agent_id == agent_id)
    assert agent_row.unresolved_count == service_row.unresolved_count
