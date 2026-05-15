import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class ProductivityCommit(Base):
    __tablename__ = "productivity_commits"

    __table_args__ = (
        UniqueConstraint(
            "connection_id", "hash", "repository",
            name="uq_commit_connection_hash_repo",
        ),
        Index("ix_prod_commits_connection", "connection_id"),
        Index("ix_prod_commits_date", "connection_id", "date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True), ForeignKey("productivity_connections.id"), nullable=False
    )
    hash = Column(String(40), nullable=False)
    short_hash = Column(String(7), nullable=False)
    message = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    additions = Column(Integer, nullable=False, default=0)
    deletions = Column(Integer, nullable=False, default=0)
    repository = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(String, nullable=True)
    is_merge = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    connection = relationship("ProductivityConnection", back_populates="commits")
