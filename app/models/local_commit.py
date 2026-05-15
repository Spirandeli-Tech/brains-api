import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class LocalCommit(Base):
    __tablename__ = "local_commits"

    __table_args__ = (
        UniqueConstraint("hash", "remote_url", name="uq_local_commits_hash_remote"),
        Index("ix_local_commits_committed_at", "committed_at"),
        Index("ix_local_commits_email", "email"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hash = Column(String(40), nullable=False)
    short_hash = Column(String(7), nullable=False)
    message = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    email = Column(String, nullable=False)
    committed_at = Column(DateTime(timezone=True), nullable=False)
    branch = Column(String, nullable=False)
    additions = Column(Integer, nullable=False, default=0)
    deletions = Column(Integer, nullable=False, default=0)
    repo_name = Column(String, nullable=False)
    remote_url = Column(String, nullable=False, default="", server_default="")
    source = Column(String, nullable=False, default="qwe", server_default="qwe")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
