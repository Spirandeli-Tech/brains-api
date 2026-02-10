import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    __table_args__ = (
        UniqueConstraint("created_by_user_id", "label", name="uq_bank_account_user_label"),
        Index("ix_bank_accounts_created_by_user_id", "created_by_user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    label = Column(String, nullable=False)
    beneficiary_full_name = Column(String, nullable=False)
    beneficiary_full_address = Column(String, nullable=True)
    beneficiary_account_number = Column(String, nullable=False)
    swift_code = Column(String, nullable=False)
    bank_name = Column(String, nullable=True)
    bank_address = Column(String, nullable=True)
    intermediary_bank_info = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
