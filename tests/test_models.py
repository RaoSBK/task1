"""Tests for database models, constraints, relationships, and foreign keys."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import UserRole, TicketStatus, TicketPriority
from app.models.user import User
from app.models.ticket import Ticket
from app.models.comment import Comment
from app.models.ticket_history import TicketHistory
from app.core.security import hash_password


def test_create_user_with_valid_roles(db_session: Session):
    """Verify users can be created with each valid role: customer, agent, admin."""
    for role in [UserRole.CUSTOMER, UserRole.AGENT, UserRole.ADMIN]:
        user = User(
            name=f"User {role.value}",
            email=f"{role.value}@example.com",
            password_hash=hash_password("securepassword123"),
            role=role,
        )
        db_session.add(user)
        db_session.flush()
        assert user.id is not None
        assert user.role == role
        assert user.created_at is not None


def test_user_invalid_role_violates_check_constraint(db_session: Session):
    """Verify database check constraint rejects invalid user roles."""
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO users (name, email, password_hash, role) "
                "VALUES ('Bad User', 'bad_role@example.com', 'hashed', 'invalid')"
            )
        )
        db_session.flush()
    db_session.rollback()


def test_user_unique_email_constraint(db_session: Session):
    """Verify unique constraint on user email address."""
    user1 = User(
        name="User One",
        email="duplicate@example.com",
        password_hash=hash_password("pass1"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(user1)
    db_session.flush()

    user2 = User(
        name="User Two",
        email="duplicate@example.com",
        password_hash=hash_password("pass2"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_create_ticket_with_valid_statuses_and_priorities(db_session: Session):
    """Verify tickets can be created with valid statuses and priorities."""
    customer = User(
        name="Customer Alice",
        email="alice@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    agent = User(
        name="Agent Bob",
        email="bob@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.AGENT,
    )
    db_session.add_all([customer, agent])
    db_session.flush()

    # Test all statuses and priorities
    statuses = [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED]
    priorities = [TicketPriority.LOW, TicketPriority.MEDIUM, TicketPriority.HIGH, TicketPriority.URGENT]

    for status, priority in zip(statuses, priorities):
        ticket = Ticket(
            customer_id=customer.id,
            assigned_agent_id=agent.id,
            title=f"Issue with {status.value}",
            description="Detailed issue description",
            status=status,
            priority=priority,
        )
        db_session.add(ticket)
        db_session.flush()
        assert ticket.id is not None
        assert ticket.customer_id == customer.id
        assert ticket.assigned_agent_id == agent.id
        assert ticket.status == status
        assert ticket.priority == priority
        assert ticket.created_at is not None
        assert ticket.updated_at is not None


def test_ticket_assigned_agent_nullable(db_session: Session):
    """Verify ticket assigned_agent_id is nullable (unassigned ticket)."""
    customer = User(
        name="Unassigned Ticket Customer",
        email="unassigned_cust@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer)
    db_session.flush()

    ticket = Ticket(
        customer_id=customer.id,
        assigned_agent_id=None,
        title="Unassigned Ticket",
        description="Waiting for agent assignment",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
    )
    db_session.add(ticket)
    db_session.flush()
    assert ticket.id is not None
    assert ticket.assigned_agent_id is None


def test_ticket_invalid_status_violates_check_constraint(db_session: Session):
    """Verify database check constraint rejects invalid ticket status."""
    customer = User(
        name="Customer Test",
        email="test_status_cust@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer)
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO tickets (customer_id, title, description, status, priority) "
                f"VALUES ({customer.id}, 'Invalid', 'Desc', 'pending', 'medium')"
            )
        )
        db_session.flush()
    db_session.rollback()


def test_ticket_invalid_priority_violates_check_constraint(db_session: Session):
    """Verify database check constraint rejects invalid ticket priority."""
    customer = User(
        name="Customer Test",
        email="test_priority_cust@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer)
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO tickets (customer_id, title, description, status, priority) "
                f"VALUES ({customer.id}, 'Invalid', 'Desc', 'open', 'extreme')"
            )
        )
        db_session.flush()
    db_session.rollback()


def test_ticket_foreign_key_customer_id_enforced(db_session: Session):
    """Verify foreign key constraint when customer_id does not exist."""
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO tickets (customer_id, title, description, status, priority) "
                "VALUES (999999, 'Invalid FK', 'Desc', 'open', 'medium')"
            )
        )
        db_session.flush()
    db_session.rollback()


def test_comment_creation_and_relationships(db_session: Session):
    """Verify comment creation and bidirectional relationships."""
    customer = User(
        name="Commenter User",
        email="commenter@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer)
    db_session.flush()

    ticket = Ticket(
        customer_id=customer.id,
        title="Ticket for comments",
        description="Needs clarification",
    )
    db_session.add(ticket)
    db_session.flush()

    comment = Comment(
        ticket_id=ticket.id,
        author_id=customer.id,
        body="This is an informative comment explaining the issue.",
    )
    db_session.add(comment)
    db_session.flush()

    assert comment.id is not None
    assert comment.created_at is not None
    assert comment.ticket.id == ticket.id
    assert comment.author.id == customer.id
    assert len(ticket.comments) == 1
    assert ticket.comments[0].id == comment.id
    assert len(customer.comments) == 1


def test_ticket_history_transitions_and_relationships(db_session: Session):
    """Verify ticket history creation, valid status transitions, and relations."""
    customer = User(
        name="History Customer",
        email="history_cust@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    agent = User(
        name="History Agent",
        email="history_agent@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.AGENT,
    )
    db_session.add_all([customer, agent])
    db_session.flush()

    ticket = Ticket(
        customer_id=customer.id,
        assigned_agent_id=agent.id,
        title="History test ticket",
        description="Checking transitions",
        status=TicketStatus.OPEN,
    )
    db_session.add(ticket)
    db_session.flush()

    # First transition: None -> OPEN (initial creation log)
    history1 = TicketHistory(
        ticket_id=ticket.id,
        changed_by=customer.id,
        old_status=None,
        new_status=TicketStatus.OPEN,
    )
    # Second transition: OPEN -> IN_PROGRESS
    history2 = TicketHistory(
        ticket_id=ticket.id,
        changed_by=agent.id,
        old_status=TicketStatus.OPEN,
        new_status=TicketStatus.IN_PROGRESS,
    )
    db_session.add_all([history1, history2])
    db_session.flush()

    assert history1.id is not None
    assert history2.id is not None
    assert history1.old_status is None
    assert history1.new_status == TicketStatus.OPEN
    assert history2.old_status == TicketStatus.OPEN
    assert history2.new_status == TicketStatus.IN_PROGRESS
    assert len(ticket.history) == 2
    assert history2.changed_by_user.id == agent.id


def test_ticket_history_invalid_status_violates_check_constraint(db_session: Session):
    """Verify database check constraint rejects invalid statuses in history table."""
    customer = User(
        name="User Hist",
        email="user_hist@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer)
    db_session.flush()

    ticket = Ticket(
        customer_id=customer.id,
        title="Ticket",
        description="Desc",
    )
    db_session.add(ticket)
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO ticket_history (ticket_id, changed_by, old_status, new_status) "
                f"VALUES ({ticket.id}, {customer.id}, 'open', 'invalid')"
            )
        )
        db_session.flush()
    db_session.rollback()


def test_cascade_delete_ticket_removes_comments_and_history(db_session: Session):
    """Verify deleting a ticket cascades to comments and ticket_history."""
    user = User(
        name="Cascade Test User",
        email="cascade@example.com",
        password_hash=hash_password("secret"),
        role=UserRole.CUSTOMER,
    )
    db_session.add(user)
    db_session.flush()

    ticket = Ticket(
        customer_id=user.id,
        title="To be deleted",
        description="Delete me",
    )
    db_session.add(ticket)
    db_session.flush()

    comment = Comment(
        ticket_id=ticket.id,
        author_id=user.id,
        body="This will be deleted with ticket",
    )
    history = TicketHistory(
        ticket_id=ticket.id,
        changed_by=user.id,
        old_status=None,
        new_status=TicketStatus.OPEN,
    )
    db_session.add_all([comment, history])
    db_session.flush()

    comment_id = comment.id
    history_id = history.id
    ticket_id = ticket.id

    # Delete ticket
    db_session.delete(ticket)
    db_session.flush()

    # Comments and history should be deleted by CASCADE
    assert db_session.get(Comment, comment_id) is None
    assert db_session.get(TicketHistory, history_id) is None
    # User should still exist
    assert db_session.get(User, user.id) is not None
