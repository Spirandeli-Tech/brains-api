import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, String, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Invoice(Base):
    __tablename__ = "invoices"

    __table_args__ = (
        UniqueConstraint("created_by_user_id", "invoice_number", name="uq_invoice_user_number"),
        Index("ix_invoices_created_by_user_id", "created_by_user_id"),
        Index("ix_invoices_user_customer", "created_by_user_id", "customer_id"),
        Index("ix_invoices_bank_account", "bank_account_id"),
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
    invoice_number = Column(String, nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(String, nullable=False, default="draft")
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    is_recurrent = Column(Boolean, nullable=False, default=False)
    recurrence_frequency = Column(String, nullable=True)
    recurrence_day = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Deprecated columns — kept for migration safety, no longer used
    service_title = Column(String, nullable=True)
    service_description = Column(Text, nullable=True)
    amount_total = Column(Numeric(12, 2), nullable=True)

    customer = relationship("Customer", back_populates="invoices", lazy="joined")
    bank_account = relationship("BankAccount", lazy="joined")
    services = relationship(
        "InvoiceService",
        back_populates="invoice",
        lazy="joined",
        cascade="all, delete-orphan",
        order_by="InvoiceService.sort_order",
    )
