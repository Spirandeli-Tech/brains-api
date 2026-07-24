import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class VideoScript(Base):
    """A version of a video's script — the "Roteiro" tab of the video detail page.

    Versioned rather than a single column on `Video` because scripts get
    rewritten, and comparing v1 against v3 is exactly the kind of thing that
    teaches. `version` is per-video and monotonic; the newest is what the UI
    shows first.

    Written either by hand or by the `/social-roteirizar-ideia` skill, which also
    fills `growth_checklist` with its item-by-item pass over
    `brand/principios-video.md` and `short_cuts` with the Short cuts named
    *before* recording (principle #7).
    """

    __tablename__ = "video_scripts"

    __table_args__ = (
        UniqueConstraint("video_id", "version", name="uq_video_scripts_video_id_version"),
        Index("ix_video_scripts_video_id", "video_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id = Column(
        UUID(as_uuid=True),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
    )

    version = Column(Integer, nullable=False, default=1, server_default="1")

    # The script itself, markdown, with the [VISUAL: ...] markers
    body = Column(Text, nullable=False)

    # list[str] — the 3 title options
    titles = Column(JSONB, nullable=False, default=list, server_default="[]")
    caption = Column(Text, nullable=True)
    # list[str]
    hashtags = Column(JSONB, nullable=False, default=list, server_default="[]")
    cover = Column(Text, nullable=True)
    # The verses/data used, for a quick check before recording
    facts_used = Column(Text, nullable=True)

    # list[{item, status, reason}] — the growth checklist gate result
    growth_checklist = Column(JSONB, nullable=False, default=list, server_default="[]")
    # list[str] — the Short cuts foreseen before recording
    short_cuts = Column(JSONB, nullable=False, default=list, server_default="[]")

    # Which persona file produced it (persona-empreendedor | persona-fe)
    persona = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    video = relationship("Video", back_populates="scripts")
