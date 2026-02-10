import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class InvoiceService(Base):
    __tablename__ = "invoice_services"

    __table_args__ = (
        Index("ix_invoice_services_created_by_user_id", "created_by_user_id"),
        Index("ix_invoice_services_invoice_id", "invoice_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    invoice_id = Column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    service_title = Column(String, nullable=False)
    service_description = Column(Text, nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    invoice = relationship("Invoice", back_populates="services")
