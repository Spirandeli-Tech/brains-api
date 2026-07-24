import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    firebase_id = Column(String, unique=True, index=True, nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("user_roles.id"), nullable=True)
    photo_url = Column(String, nullable=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Soft delete: 19 of the 20 FKs pointing here are NO ACTION, so a hard
    # delete would either fail or force destroying legitimate history. A
    # deleted user disappears from listings and cannot authenticate, but every
    # row it owns stays intact and the decision stays reversible.
    deleted_at = Column(DateTime, nullable=True, index=True)

    role = relationship("UserRole", lazy="joined")
