"""Generic base service for CRUD and transactional operations."""

from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseService(Generic[ModelType]):
    """Base service encapsulating standard database operations."""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        """Fetch a single record by primary key."""
        return db.get(self.model, id)

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Fetch multiple records with pagination."""
        statement = select(self.model).offset(skip).limit(limit)
        return list(db.scalars(statement).all())

    def create(self, db: Session, *, obj_in: dict[str, Any]) -> ModelType:
        """Create and commit a new record."""
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: Any) -> Optional[ModelType]:
        """Delete a record by primary key."""
        obj = db.get(self.model, id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj
