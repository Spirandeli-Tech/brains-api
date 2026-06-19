import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class ProductivityConnection(Base):
    __tablename__ = "productivity_connections"

    __table_args__ = (
        UniqueConstraint(
            "created_by_user_id", "provider", "username", "workspace",
            name="uq_connection_user_provider_workspace",
        ),
        Index("ix_prod_connections_user", "created_by_user_id"),
        Index("ix_prod_connections_contract", "contract_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    provider = Column(String, nullable=False)  # "github" or "bitbucket"
    pat_encrypted = Column(Text, nullable=False)
    username = Column(String, nullable=False)
    workspace = Column(String, nullable=True)
    # Stable provider-side identifier captured at setup (Bitbucket account_id,
    # GitHub user id). Used to filter commits authored by this account without
    # relying on display-name/nickname matches.
    external_account_id = Column(String, nullable=True)
    contract_id = Column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=True
    )
    custom_name = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
    selected_repos = Column(JSONB, nullable=True, default=list)
    is_primary = Column(Boolean, nullable=False, default=False, server_default="false")
    last_synced_at = Column(DateTime, nullable=True)
    # Per-repository sync watermark: {repo_full_name: ISO-8601 timestamp}. Lets a
    # newly-added repo get its own backfill instead of inheriting the connection's
    # last_synced_at (which would skip everything committed before the repo was added).
    repo_synced_at = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    contract = relationship("Contract", lazy="joined")
    commits = relationship(
        "ProductivityCommit",
        back_populates="connection",
        cascade="all, delete-orphan",
    )
    pull_requests = relationship(
        "ProductivityPullRequest",
        back_populates="connection",
        cascade="all, delete-orphan",
    )
