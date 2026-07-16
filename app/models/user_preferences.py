import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.db import Base


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    report_theme_color = Column(String, nullable=True, default="#1677ff")
    report_header_image_url = Column(String, nullable=True)
    default_currency = Column(String, nullable=True, default="USD")
    # "Insights for Today" scheduled trigger (fase 4a). When enabled, the
    # scheduler pre-warms the day's plan once the hour passes; the lazy trigger
    # (GET /insights) covers the common case where the Mac was off at that hour.
    # planner_hour is a 0-23 UTC hour for now (timezone refinement deferred).
    planner_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    planner_hour = Column(Integer, nullable=False, default=7, server_default="7")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
