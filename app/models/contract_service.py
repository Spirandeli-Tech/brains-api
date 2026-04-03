import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class ContractService(Base):
    __tablename__ = "contract_services"

    __table_args__ = (
        Index("ix_contract_services_created_by_user_id", "created_by_user_id"),
        Index("ix_contract_services_contract_id", "contract_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    contract_id = Column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    service_title = Column(String, nullable=False)
    service_description = Column(Text, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    contract = relationship("Contract", back_populates="services")
