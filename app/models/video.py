import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Video(Base):
    """A row in the publication calendar — one piece to record and publish.

    Owns everything the old sheet couldn't: the publish date, the pipeline
    status, the thumb, and the 48h metrics. Those metrics matter beyond
    reporting: `brand/principios-video.md` says every growth principle stays a
    *hypothesis* until CTR and retention confirm it, so this table is what
    closes that loop.

    `status` is a pipeline, not a flag — the ordered states live in
    `app.services.content_service.VIDEO_STATUSES`. Answering "where did I get
    stuck?" is the point.
    """

    __tablename__ = "videos"

    __table_args__ = (
        Index("ix_videos_user_id", "user_id"),
        Index("ix_videos_status", "status"),
        Index("ix_videos_publish_date", "publish_date"),
        Index("ix_videos_idea_id", "idea_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    idea_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="SET NULL"),
        nullable=True,
    )

    title = Column(String, nullable=False)
    slug = Column(String, nullable=True)
    # The single expression we want to own in search (principle #6). Repeated in
    # the first 5s, the middle, the close, the title and the description.
    keyword = Column(String, nullable=True)

    # short | video — the two tiers of principle #7 (Short captures, longer
    # piece deepens)
    format = Column(String, nullable=False, default="short", server_default="short")

    series = Column(String, nullable=True)
    episode_number = Column(Integer, nullable=True)

    publish_date = Column(Date, nullable=True)
    # idea | script_ready | recorded | edited | published
    status = Column(String, nullable=False, default="idea", server_default="idea")

    thumb_url = Column(Text, nullable=True)
    youtube_url = Column(Text, nullable=True)

    ctr_48h = Column(Numeric(6, 2), nullable=True)
    retention_48h = Column(Numeric(6, 2), nullable=True)
    learning = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    idea = relationship("Idea", back_populates="videos", lazy="joined")
    scripts = relationship(
        "VideoScript",
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="desc(VideoScript.version)",
    )
