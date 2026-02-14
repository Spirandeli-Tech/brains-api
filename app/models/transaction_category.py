import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class TransactionCategory(Base):
    __tablename__ = "transaction_categories"

    __table_args__ = (
        UniqueConstraint(
            "created_by_user_id", "name", name="uq_transaction_category_user_name"
        ),
        Index(
            "ix_transaction_categories_created_by_user_id", "created_by_user_id"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name = Column(String, nullable=False)
    color = Column(String(7), nullable=True)
    icon = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
