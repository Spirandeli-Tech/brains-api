"""Business logic for the content pipeline: ideas → videos → scripts.

Replaces the two tabs of the old Google Sheet (`Banco` and `Roteiros`), but cut
along a different line. The sheet's `Banco` mixed idea fields with publication
fields, which is why its `ctr_48h`/`retencao_48h` columns were never filled: you
open an idea list to pick a topic, not to measure a result. Here the idea keeps
the *pauta* and the video keeps the calendar and the metrics.

The metrics are not decoration. `brand/principios-video.md` (the channel growth
checklist) states that every principle it lists stays a hypothesis until CTR and
retention confirm it — so `Video.ctr_48h` / `Video.retention_48h` are what turn
that file from a wish list into something falsifiable.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.idea import Idea
from app.models.user import User
from app.models.video import Video
from app.models.video_script import VideoScript

# The pipeline, in order. The UI colours the status column with this — the point
# is answering "where did I get stuck?", which is the real question when a
# channel stops publishing.
VIDEO_STATUSES = ["idea", "script_ready", "recorded", "edited", "published"]

IDEA_STATUSES = ["idea", "review", "promoted", "discarded"]


def _slugify(value: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return cleaned[:80] or "sem-titulo"


def resolve_user_id(db: Session, email: str) -> UUID:
    """Runner endpoints have no session, and this database has several users —
    so the caller names the user and we fail loudly if it does not exist."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user with email {email}",
        )
    return user.id


# --- Ideas ---


def _serialize_idea(idea: Idea, video_count: int | None = None) -> dict:
    return {
        "id": idea.id,
        "slug": idea.slug,
        "title": idea.title,
        "format": idea.format,
        "type": idea.type,
        "priority": idea.priority,
        "status": idea.status,
        "hook": idea.hook,
        "why_now": idea.why_now,
        "visual_refs": idea.visual_refs,
        "trustworthy": idea.trustworthy,
        "fact_check": idea.fact_check,
        "theme_filter": idea.theme_filter or {},
        "source": idea.source,
        "video_count": video_count if video_count is not None else len(idea.videos),
        "created_at": idea.created_at,
        "updated_at": idea.updated_at,
    }


def list_ideas(db: Session, user_id: UUID, status_filter: str | None = None) -> list[dict]:
    counts = dict(
        db.query(Video.idea_id, func.count(Video.id))
        .filter(Video.user_id == user_id, Video.idea_id.isnot(None))
        .group_by(Video.idea_id)
        .all()
    )
    query = db.query(Idea).filter(Idea.user_id == user_id)
    if status_filter:
        query = query.filter(Idea.status == status_filter)
    ideas = query.order_by(Idea.created_at.desc()).all()
    return [_serialize_idea(i, counts.get(i.id, 0)) for i in ideas]


def list_idea_topics(db: Session, user_id: UUID) -> list[Idea]:
    """Every idea, any status — this is the anti-repetition memory that
    `/social-buscar-trends` dedups against."""
    return (
        db.query(Idea)
        .filter(Idea.user_id == user_id)
        .order_by(Idea.created_at.asc())
        .all()
    )


def get_idea(db: Session, user_id: UUID, idea_id: UUID) -> dict:
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user_id).first()
    if not idea:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")
    return _serialize_idea(idea)


def create_idea(db: Session, user_id: UUID, data: dict) -> dict:
    idea = Idea(
        user_id=user_id,
        title=data["title"],
        slug=data.get("slug") or _slugify(data["title"]),
        format=data.get("format") or "short",
        type=data.get("type"),
        priority=data.get("priority") or "media",
        status=data.get("status") or "idea",
        hook=data.get("hook"),
        why_now=data.get("why_now"),
        visual_refs=data.get("visual_refs"),
        trustworthy=True if data.get("trustworthy") is None else data["trustworthy"],
        fact_check=data.get("fact_check"),
        theme_filter=data.get("theme_filter") or {},
        source=data.get("source") or "manual",
    )
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return _serialize_idea(idea, 0)


def create_ideas_bulk(db: Session, user_id: UUID, items: list[dict]) -> list[dict]:
    created = []
    for item in items:
        idea = Idea(
            user_id=user_id,
            title=item["title"],
            slug=item.get("slug") or _slugify(item["title"]),
            format=item.get("format") or "short",
            type=item.get("type"),
            priority=item.get("priority") or "media",
            # An idea whose fact-check left something pending must not slide
            # into scripting unnoticed — it lands as `review`.
            status=item.get("status")
            or ("review" if item.get("trustworthy") is False else "idea"),
            hook=item.get("hook"),
            why_now=item.get("why_now"),
            visual_refs=item.get("visual_refs"),
            trustworthy=True if item.get("trustworthy") is None else item["trustworthy"],
            fact_check=item.get("fact_check"),
            theme_filter=item.get("theme_filter") or {},
            source=item.get("source") or "buscar-trends",
        )
        db.add(idea)
        created.append(idea)
    db.commit()
    for idea in created:
        db.refresh(idea)
    return [_serialize_idea(i, 0) for i in created]


def update_idea(db: Session, user_id: UUID, idea_id: UUID, data: dict) -> dict:
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user_id).first()
    if not idea:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")
    for field, value in data.items():
        if value is not None:
            setattr(idea, field, value)
    db.commit()
    db.refresh(idea)
    return _serialize_idea(idea)


def delete_idea(db: Session, user_id: UUID, idea_id: UUID) -> None:
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user_id).first()
    if not idea:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")
    db.delete(idea)
    db.commit()


def promote_idea(db: Session, user_id: UUID, idea_id: UUID, data: dict) -> dict:
    """Turn an idea into a calendar row.

    This is the gesture that used to be copy-and-paste between a spreadsheet and
    your head. The video inherits title and keyword; the idea is marked
    `promoted` but kept — one idea legitimately spawns several videos (the Short
    and the longer piece share a theme, principle #7), so promoting twice is
    allowed on purpose.
    """
    idea = db.query(Idea).filter(Idea.id == idea_id, Idea.user_id == user_id).first()
    if not idea:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    video = Video(
        user_id=user_id,
        idea_id=idea.id,
        title=idea.title,
        slug=idea.slug,
        keyword=data.get("keyword"),
        format=data.get("format") or idea.format or "short",
        series=data.get("series"),
        episode_number=data.get("episode_number"),
        publish_date=data.get("publish_date"),
        status="idea",
    )
    db.add(video)
    idea.status = "promoted"
    db.commit()
    db.refresh(video)
    return _serialize_video(video, 0)


# --- Videos ---


def _serialize_video(video: Video, script_count: int | None = None) -> dict:
    return {
        "id": video.id,
        "idea_id": video.idea_id,
        "idea_title": video.idea.title if video.idea else None,
        "title": video.title,
        "slug": video.slug,
        "keyword": video.keyword,
        "format": video.format,
        "series": video.series,
        "episode_number": video.episode_number,
        "publish_date": video.publish_date,
        "status": video.status,
        "thumb_url": video.thumb_url,
        "youtube_url": video.youtube_url,
        "ctr_48h": video.ctr_48h,
        "retention_48h": video.retention_48h,
        "learning": video.learning,
        "script_count": script_count if script_count is not None else len(video.scripts),
        "created_at": video.created_at,
        "updated_at": video.updated_at,
    }


def _serialize_script(script: VideoScript) -> dict:
    return {
        "id": script.id,
        "video_id": script.video_id,
        "version": script.version,
        "body": script.body,
        "titles": script.titles or [],
        "caption": script.caption,
        "hashtags": script.hashtags or [],
        "cover": script.cover,
        "facts_used": script.facts_used,
        "growth_checklist": script.growth_checklist or [],
        "short_cuts": script.short_cuts or [],
        "persona": script.persona,
        "created_at": script.created_at,
    }


def list_videos(db: Session, user_id: UUID, status_filter: str | None = None) -> list[dict]:
    counts = dict(
        db.query(VideoScript.video_id, func.count(VideoScript.id))
        .join(Video, Video.id == VideoScript.video_id)
        .filter(Video.user_id == user_id)
        .group_by(VideoScript.video_id)
        .all()
    )
    query = db.query(Video).filter(Video.user_id == user_id)
    if status_filter:
        query = query.filter(Video.status == status_filter)
    # Undated rows sort last: a calendar reads forwards, and "not scheduled yet"
    # is the tail, not the head.
    videos = query.order_by(Video.publish_date.asc().nullslast(), Video.created_at.desc()).all()
    return [_serialize_video(v, counts.get(v.id, 0)) for v in videos]


def get_video(db: Session, user_id: UUID, video_id: UUID) -> dict:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    payload = _serialize_video(video)
    payload["scripts"] = [_serialize_script(s) for s in video.scripts]
    return payload


def create_video(db: Session, user_id: UUID, data: dict) -> dict:
    video = Video(
        user_id=user_id,
        idea_id=data.get("idea_id"),
        title=data["title"],
        slug=data.get("slug") or _slugify(data["title"]),
        keyword=data.get("keyword"),
        format=data.get("format") or "short",
        series=data.get("series"),
        episode_number=data.get("episode_number"),
        publish_date=data.get("publish_date"),
        status=data.get("status") or "idea",
        thumb_url=data.get("thumb_url"),
        youtube_url=data.get("youtube_url"),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return _serialize_video(video, 0)


def update_video(db: Session, user_id: UUID, video_id: UUID, data: dict) -> dict:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    for field, value in data.items():
        if value is not None:
            setattr(video, field, value)
    db.commit()
    db.refresh(video)
    return _serialize_video(video)


def delete_video(db: Session, user_id: UUID, video_id: UUID) -> None:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    db.delete(video)
    db.commit()


# --- Scripts ---


def list_scripts(db: Session, user_id: UUID, video_id: UUID) -> list[dict]:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return [_serialize_script(s) for s in video.scripts]


def create_script(db: Session, user_id: UUID, video_id: UUID, data: dict) -> dict:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    current_max = (
        db.query(func.max(VideoScript.version)).filter(VideoScript.video_id == video_id).scalar()
    )
    script = VideoScript(
        video_id=video.id,
        version=(current_max or 0) + 1,
        body=data["body"],
        titles=data.get("titles") or [],
        caption=data.get("caption"),
        hashtags=data.get("hashtags") or [],
        cover=data.get("cover"),
        facts_used=data.get("facts_used"),
        growth_checklist=data.get("growth_checklist") or [],
        short_cuts=data.get("short_cuts") or [],
        persona=data.get("persona"),
    )
    db.add(script)
    # A video that just got its first script is no longer just an idea. Later
    # states are never walked backwards by this.
    if video.status == "idea":
        video.status = "script_ready"
    db.commit()
    db.refresh(script)
    return _serialize_script(script)


def delete_script(db: Session, user_id: UUID, video_id: UUID, script_id: UUID) -> None:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    script = (
        db.query(VideoScript)
        .filter(VideoScript.id == script_id, VideoScript.video_id == video_id)
        .first()
    )
    if not script:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    db.delete(script)
    db.commit()
