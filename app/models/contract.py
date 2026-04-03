import uuid
from datetime import datetime

from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Contract(Base):
    __tablename__ = "contracts"

    __table_args__ = (
        UniqueConstraint("created_by_user_id", "name", name="uq_contract_user_name"),
        Index("ix_contracts_created_by_user_id", "created_by_user_id"),
        Index("ix_contracts_customer_id", "created_by_user_id", "customer_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    customer_id = Column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    bank_account_id = Column(
        UUID(as_uuid=True), ForeignKey("bank_accounts.id"), nullable=True
    )
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")  # active, inactive
    annual_value = Column(Numeric(12, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="USD")
    invoice_day = Column(Integer, nullable=False, default=1)  # 1-31
    notes = Column(Text, nullable=True)
    contract_pdf_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer = relationship("Customer", lazy="joined")
    bank_account = relationship("BankAccount", lazy="joined")
    services = relationship(
        "ContractService",
        back_populates="contract",
        lazy="joined",
        cascade="all, delete-orphan",
        order_by="ContractService.sort_order",
    )
