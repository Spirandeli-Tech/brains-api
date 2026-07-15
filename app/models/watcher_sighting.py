import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class WatcherSighting(Base):
    """Dedup record: one row per (watcher, external_key) so a PR/ticket the
    watcher sees on every tick only ever triggers one run."""

    __tablename__ = "watcher_sightings"

    __table_args__ = (
        UniqueConstraint("watcher_id", "external_key", name="uq_watcher_sighting_key"),
        Index("ix_watcher_sightings_watcher_id", "watcher_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watcher_id = Column(UUID(as_uuid=True), ForeignKey("watchers.id", ondelete="CASCADE"), nullable=False)
    external_key = Column(String, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    handled_ref = Column(String, nullable=True)

    watcher = relationship("Watcher", back_populates="sightings")
