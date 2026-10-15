"""Tests for authentication, registration, Argon2 hashing, JWT tokens, and RBAC."""

from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token
from app.models.enums import UserRole
from app.models.user import User
from app.services.user import user_service
from app.cli import create_user_command, bootstrap_admin_command
import argparse


def test_argon2_password_hashing_and_verification():
    """Verify passwords are securely hashed using Argon2id and verified correctly."""
    plain = "SuperSecurePassword123!"
    hashed = hash_password(plain)

    # Verify Argon2id format
    assert hashed.startswith("$argon2id$")
    # Verify correctness
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(plain, "") is False


def test_customer_registration_success(client: TestClient, db_session: Session):
    """Verify customer registration creates user with customer role and returns 201."""
    payload = {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "password": "ValidPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Jane Doe"
    assert data["email"] == "jane.doe@example.com"
    assert data["role"] == "customer"
    assert "id" in data
    assert "created_at" in data

    # Verify password hash is NEVER exposed in response
    assert "password" not in data
    assert "password_hash" not in data

    # Verify database state
    user = user_service.get_by_email(db_session, "jane.doe@example.com")
    assert user is not None
    assert user.role == UserRole.CUSTOMER
    assert user.password_hash.startswith("$argon2id$")


def test_customer_registration_duplicate_email_conflict(client: TestClient):
    """Verify duplicate email registration returns 409 Conflict."""
    payload = {
        "name": "First User",
        "email": "duplicate@example.com",
        "password": "Password123!",
    }
    r1 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201

    # Attempt to register again with same email
    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409
    assert "already registered" in r2.json()["detail"].lower()


def test_customer_registration_role_escalation_prevented(client: TestClient, db_session: Session):
    """Verify public registration ignores or rejects role escalation attempts."""
    payload = {
        "name": "Escalation Attacker",
        "email": "attacker@example.com",
        "password": "Password123!",
        "role": "admin",  # Maliciously attempt to set role to admin
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    # The created role must strictly be 'customer', never 'admin'
    assert data["role"] == "customer"

    # Confirm in database
    user = user_service.get_by_email(db_session, "attacker@example.com")
    assert user is not None
    assert user.role == UserRole.CUSTOMER


def test_customer_registration_invalid_email_format(client: TestClient):
    """Verify invalid email syntax returns 422 Unprocessable Entity."""
    payload = {
        "name": "Invalid Email",
        "email": "not-a-valid-email",
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_customer_registration_password_too_short(client: TestClient):
    """Verify passwords shorter than 8 characters are rejected with 422."""
    payload = {
        "name": "Short Pass",
        "email": "short@example.com",
        "password": "Pass1",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_customer_registration_password_missing_number(client: TestClient):
    """Verify passwords without numbers are rejected with 422."""
    payload = {
        "name": "No Number",
        "email": "nonumber@example.com",
        "password": "PasswordWithoutDigits",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_login_success(client: TestClient):
    """Verify successful login returns signed JWT access token and user info."""
    # Register user first
    reg_payload = {
        "name": "Login User",
        "email": "login_user@example.com",
        "password": "ValidLoginPassword123!",
    }
    client.post("/api/v1/auth/register", json=reg_payload)

    # Login
    login_payload = {
        "email": "login_user@example.com",
        "password": "ValidLoginPassword123!",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["email"] == "login_user@example.com"
    assert data["user"]["role"] == "customer"
    assert "password_hash" not in data["user"]


def test_login_nonexistent_email_returns_401(client: TestClient):
    """Verify login with unregistered email returns 401 Unauthorized."""
    payload = {
        "email": "ghost@example.com",
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "incorrect email or password" in response.json()["detail"].lower()


def test_login_wrong_password_returns_401(client: TestClient):
    """Verify login with incorrect password returns 401 Unauthorized."""
    reg_payload = {
        "name": "Wrong Pass User",
        "email": "wrongpass@example.com",
        "password": "CorrectPassword123!",
    }
    client.post("/api/v1/auth/register", json=reg_payload)

    login_payload = {
        "email": "wrongpass@example.com",
        "password": "IncorrectPassword123!",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "incorrect email or password" in response.json()["detail"].lower()


def test_get_current_user_profile(client: TestClient):
    """Verify /me endpoint returns authenticated user profile."""
    reg_payload = {
        "name": "Me User",
        "email": "me@example.com",
        "password": "ValidPassword123!",
    }
    client.post("/api/v1/auth/register", json=reg_payload)

    login_res = client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "ValidPassword123!"})
    token = login_res.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["name"] == "Me User"
    assert data["role"] == "customer"
    assert "password_hash" not in data


def test_get_current_user_unauthenticated_returns_401(client: TestClient):
    """Verify accessing protected endpoint without token returns 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_get_current_user_invalid_token_returns_401(client: TestClient):
    """Verify accessing protected endpoint with corrupted token returns 401."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.malformed.token"},
    )
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_get_current_user_expired_token_returns_401(client: TestClient, db_session: Session):
    """Verify expired token returns 401 with expired message."""
    user = user_service.create_customer(
        db_session,
        name="Expired User",
        email="expired@example.com",
        password="Password123!",
    )
    # Generate expired token
    expired_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(seconds=-10),
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_rbac_admin_endpoint_allows_admin(client: TestClient, db_session: Session):
    """Verify admin-only endpoint allows user with admin role."""
    admin = user_service.create_user_with_role(
        db_session,
        name="Site Admin",
        email="admin_rbac@example.com",
        password="AdminPassword123!",
        role=UserRole.ADMIN,
    )
    admin_role_str = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    token = create_access_token(subject=admin.id, extra_claims={"role": admin_role_str})

    response = client.get(
        "/api/v1/auth/admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "Hello Admin" in response.json()["message"]


def test_rbac_admin_endpoint_forbids_customer(client: TestClient, db_session: Session):
    """Verify admin-only endpoint returns 403 Forbidden for customer role."""
    customer = user_service.create_customer(
        db_session,
        name="Normal Customer",
        email="customer_rbac@example.com",
        password="CustomerPassword123!",
    )
    cust_role_str = customer.role.value if hasattr(customer.role, "value") else str(customer.role)
    token = create_access_token(subject=customer.id, extra_claims={"role": cust_role_str})

    response = client.get(
        "/api/v1/auth/admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "insufficient permissions" in response.json()["detail"].lower()


def test_rbac_agent_endpoint_allows_agent_and_admin(client: TestClient, db_session: Session):
    """Verify agent endpoint allows both agent and admin roles."""
    agent = user_service.create_user_with_role(
        db_session,
        name="Support Agent",
        email="agent_rbac@example.com",
        password="AgentPassword123!",
        role=UserRole.AGENT,
    )
    admin = user_service.create_user_with_role(
        db_session,
        name="Admin Agent",
        email="admin_agent_rbac@example.com",
        password="AdminPassword123!",
        role=UserRole.ADMIN,
    )

    agent_role_str = agent.role.value if hasattr(agent.role, "value") else str(agent.role)
    admin_role_str = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    agent_token = create_access_token(subject=agent.id, extra_claims={"role": agent_role_str})
    admin_token = create_access_token(subject=admin.id, extra_claims={"role": admin_role_str})

    res1 = client.get("/api/v1/auth/agent-only", headers={"Authorization": f"Bearer {agent_token}"})
    assert res1.status_code == 200

    res2 = client.get("/api/v1/auth/agent-only", headers={"Authorization": f"Bearer {admin_token}"})
    assert res2.status_code == 200


def test_rbac_agent_endpoint_forbids_customer(client: TestClient, db_session: Session):
    """Verify agent endpoint returns 403 Forbidden for customer role."""
    customer = user_service.create_customer(
        db_session,
        name="Customer",
        email="cust_agent_rbac@example.com",
        password="Password123!",
    )
    cust_role_str = customer.role.value if hasattr(customer.role, "value") else str(customer.role)
    token = create_access_token(subject=customer.id, extra_claims={"role": cust_role_str})

    response = client.get(
        "/api/v1/auth/agent-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "insufficient permissions" in response.json()["detail"].lower()


def test_cli_create_user_admin_and_agent(db_session: Session):
    """Verify CLI create-user command safely creates admin and agent accounts."""
    args_admin = argparse.Namespace(
        name="CLI Admin",
        email="cli_admin@example.com",
        role="admin",
        password="CliAdminPassword123!",
    )
    ret_admin = create_user_command(args_admin, db=db_session)
    assert ret_admin == 0

    admin = user_service.get_by_email(db_session, "cli_admin@example.com")
    assert admin is not None
    assert admin.role == UserRole.ADMIN
    assert verify_password("CliAdminPassword123!", admin.password_hash)

    args_agent = argparse.Namespace(
        name="CLI Agent",
        email="cli_agent@example.com",
        role="agent",
        password="CliAgentPassword123!",
    )
    ret_agent = create_user_command(args_agent, db=db_session)
    assert ret_agent == 0

    agent = user_service.get_by_email(db_session, "cli_agent@example.com")
    assert agent is not None
    assert agent.role == UserRole.AGENT


def test_cli_bootstrap_admin(db_session: Session):
    """Verify bootstrap-admin command safely creates initial administrator."""
    args = argparse.Namespace(
        name="Bootstrap Admin",
        email="bootstrap_admin@example.com",
        password="BootstrapPassword123!",
    )
    ret = bootstrap_admin_command(args, db=db_session)
    assert ret == 0

    # Running a second time should detect existing admin and cleanly exit 0
    ret_again = bootstrap_admin_command(args, db=db_session)
    assert ret_again == 0
