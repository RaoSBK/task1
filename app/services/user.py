"""User service handling registration, authentication, and user queries."""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password, verify_password
from app.services.base import BaseService


class UserService(BaseService[User]):
    """Service encapsulating user business logic."""

    def __init__(self):
        super().__init__(User)

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Fetch user by case-insensitive email."""
        statement = select(User).where(User.email == email.lower().strip())
        return db.scalar(statement)

    def create_customer(
        self, db: Session, *, name: str, email: str, password: str
    ) -> User:
        """Create a new user with strictly the CUSTOMER role."""
        normalized_email = email.lower().strip()
        hashed = hash_password(password)
        db_user = User(
            name=name.strip(),
            email=normalized_email,
            password_hash=hashed,
            role=UserRole.CUSTOMER,  # Explicitly enforced: public registration is always customer
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def create_user_with_role(
        self,
        db: Session,
        *,
        name: str,
        email: str,
        password: str,
        role: UserRole,
    ) -> User:
        """Create a user with an administrative/agent role (internal / CLI only)."""
        normalized_email = email.lower().strip()
        hashed = hash_password(password)
        db_user = User(
            name=name.strip(),
            email=normalized_email,
            password_hash=hashed,
            role=role,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def authenticate(
        self, db: Session, *, email: str, password: str
    ) -> Optional[User]:
        """Authenticate user by email and plaintext password."""
        user = self.get_by_email(db, email=email)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user


user_service = UserService()
