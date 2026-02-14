import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Transaction(Base):
    __tablename__ = "transactions"

    __table_args__ = (
        Index("ix_transactions_created_by_user_id", "created_by_user_id"),
        Index("ix_transactions_user_type", "created_by_user_id", "type"),
        Index("ix_transactions_user_context", "created_by_user_id", "context"),
        Index("ix_transactions_user_date", "created_by_user_id", "date"),
        Index("ix_transactions_bank_account", "bank_account_id"),
        Index("ix_transactions_category", "category_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    type = Column(String, nullable=False)
    context = Column(String, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    date = Column(Date, nullable=False)
    category_id = Column(
        UUID(as_uuid=True), ForeignKey("transaction_categories.id"), nullable=True
    )
    bank_account_id = Column(
        UUID(as_uuid=True), ForeignKey("bank_accounts.id"), nullable=True
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    category = relationship("TransactionCategory", lazy="joined")
    bank_account = relationship("BankAccount", lazy="joined")
