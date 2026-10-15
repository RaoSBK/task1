"""Administrative command-line interface for the Customer Support Ticket Management System."""

import sys
import argparse
import getpass
from typing import Optional
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models.enums import UserRole
from app.services.user import user_service
from app.core.config import settings
from app.schemas.user import validate_password_strength


def create_user_command(args: argparse.Namespace, db: Optional[Session] = None) -> int:
    """Create a user with an administrative, agent, or customer role."""
    name = args.name.strip()
    email = args.email.lower().strip()
    role_str = args.role.lower().strip()

    try:
        role = UserRole(role_str)
    except ValueError:
        print(f"Error: Invalid role '{role_str}'. Allowed roles: {[r.value for r in UserRole]}")
        return 1

    password = args.password
    if not password:
        password = getpass.getpass("Enter password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Error: Passwords do not match.")
            return 1

    try:
        validate_password_strength(password)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    session_owner = False
    if db is None:
        db = SessionLocal()
        session_owner = True

    try:
        existing = user_service.get_by_email(db, email=email)
        if existing:
            print(f"Error: A user with email '{email}' already exists.")
            return 1

        user = user_service.create_user_with_role(
            db,
            name=name,
            email=email,
            password=password,
            role=role,
        )
        role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
        print(f"Success: Created user '{user.name}' ({user.email}) with role '{role_str}' (ID: {user.id}).")
        return 0
    finally:
        if session_owner:
            db.close()


def bootstrap_admin_command(args: argparse.Namespace, db: Optional[Session] = None) -> int:
    """Safely bootstrap an initial administrator if one does not already exist."""
    session_owner = False
    if db is None:
        db = SessionLocal()
        session_owner = True

    try:
        # Check if any admin already exists
        from sqlalchemy import select
        from app.models.user import User

        existing_admin = db.scalar(select(User).where(User.role == UserRole.ADMIN))
        if existing_admin:
            print(f"Notice: An administrator already exists ('{existing_admin.email}'). No action taken.")
            return 0

        email = args.email or settings.INITIAL_ADMIN_EMAIL or "admin@example.com"
        name = args.name or "System Administrator"
        password = args.password or settings.INITIAL_ADMIN_PASSWORD

        if not password:
            password = getpass.getpass(f"Enter initial password for admin '{email}': ")

        try:
            validate_password_strength(password)
        except ValueError as e:
            print(f"Error: {e}")
            return 1

        admin = user_service.create_user_with_role(
            db,
            name=name,
            email=email,
            password=password,
            role=UserRole.ADMIN,
        )
        print(f"Success: Initial administrator bootstrapped: {admin.email} (ID: {admin.id}).")
        return 0
    finally:
        if session_owner:
            db.close()


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Administrative CLI for Customer Support Ticket Management System",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-user
    create_parser = subparsers.add_parser("create-user", help="Create a user with a specific role")
    create_parser.add_argument("--name", required=True, help="Full name of the user")
    create_parser.add_argument("--email", required=True, help="Unique email address")
    create_parser.add_argument(
        "--role",
        required=True,
        choices=[r.value for r in UserRole],
        help="Assigned role: customer, agent, or admin",
    )
    create_parser.add_argument("--password", required=False, default=None, help="Password (prompted if omitted)")

    # bootstrap-admin
    bootstrap_parser = subparsers.add_parser(
        "bootstrap-admin",
        help="Bootstrap initial administrator if none exists",
    )
    bootstrap_parser.add_argument("--name", required=False, default=None, help="Admin name")
    bootstrap_parser.add_argument("--email", required=False, default=None, help="Admin email")
    bootstrap_parser.add_argument("--password", required=False, default=None, help="Admin password")

    return parser


def main() -> None:
    """CLI execution entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "create-user":
        code = create_user_command(args)
    elif args.command == "bootstrap-admin":
        code = bootstrap_admin_command(args)
    else:
        parser.print_help()
        code = 1

    sys.exit(code)


if __name__ == "__main__":
    main()
