import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Idea(Base):
    """A content idea — the *pauta* half of the old Google Sheet `Banco` tab.

    Deliberately lean: everything about a *published* piece (publish date,
    thumb, CTR, retention, learning) lives on `Video`, not here. The old sheet
    mixed both jobs, which is why its metric columns were never filled in — you
    open an idea list to think about topics, not to measure results.

    Produced by the `/social-buscar-trends` skill (which fact-checks before
    writing, hence `trustworthy` + `fact_check`) or by hand in the dashboard.
    One idea can spawn several videos (a Short and a longer piece share a theme),
    so the relationship to `Video` is 1:N — see `promote_idea` in
    `app.services.content_service`.
    """

    __tablename__ = "ideas"

    __table_args__ = (
        Index("ix_ideas_user_id", "user_id"),
        Index("ix_ideas_status", "status"),
        Index("ix_ideas_slug", "slug"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # `chave_tema` in the old sheet — the short concept slug used for dedup
    slug = Column(String, nullable=False)
    title = Column(String, nullable=False)

    # short | video | message | series
    format = Column(String, nullable=False, default="short", server_default="short")
    # reflexao | ensino | devocional | testemunho | lista | historia-biblica
    type = Column(String, nullable=True)
    # alta | media | baixa
    priority = Column(String, nullable=False, default="media", server_default="media")
    # idea | review | promoted | discarded
    status = Column(String, nullable=False, default="idea", server_default="idea")

    hook = Column(Text, nullable=True)
    why_now = Column(Text, nullable=True)
    visual_refs = Column(Text, nullable=True)

    # False when the fact-check left something pending; pairs with `fact_check`,
    # which holds the verification summary and any [CHECAR: ...] markers.
    trustworthy = Column(Boolean, nullable=False, default=True, server_default="true")
    fact_check = Column(Text, nullable=True)

    # The 3-question theme gate from brand/principios-video.md (#9 demand,
    # #10 angle, #11 immediate value). Stored so that reopening an idea weeks
    # later shows *why* it passed instead of forcing you to reconstruct it.
    theme_filter = Column(JSONB, nullable=False, default=dict, server_default="{}")

    # buscar-trends | manual
    source = Column(String, nullable=False, default="manual", server_default="manual")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    videos = relationship("Video", back_populates="idea")
