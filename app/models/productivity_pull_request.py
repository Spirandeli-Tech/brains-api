import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class ProductivityPullRequest(Base):
    __tablename__ = "productivity_pull_requests"

    __table_args__ = (
        UniqueConstraint(
            "connection_id", "number", "repository",
            name="uq_pr_connection_number_repo",
        ),
        Index("ix_prod_prs_connection", "connection_id"),
        Index("ix_prod_prs_date", "connection_id", "created_at_remote"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True), ForeignKey("productivity_connections.id"), nullable=False
    )
    number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False)  # open, merged, declined, closed
    repository = Column(String, nullable=False)
    url = Column(String, nullable=False)
    created_at_remote = Column(DateTime, nullable=False)
    merged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    connection = relationship("ProductivityConnection", back_populates="pull_requests")
