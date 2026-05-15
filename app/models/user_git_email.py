import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class UserGitEmail(Base):
    __tablename__ = "user_git_emails"

    __table_args__ = (
        UniqueConstraint("user_id", "email", name="uq_user_git_emails_user_email"),
        Index("ix_user_git_emails_email", "email"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
