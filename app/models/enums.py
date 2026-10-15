"""Enumerations for User roles, Ticket statuses, and Ticket priorities."""

from enum import Enum


class UserRole(str, Enum):
    """Allowed user roles."""
    CUSTOMER = "customer"
    AGENT = "agent"
    ADMIN = "admin"


class TicketStatus(str, Enum):
    """Allowed ticket statuses."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    """Allowed ticket priorities."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
