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

from datetime import date, timedelta
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

CHECK_STATES = ["pass", "partial", "fail", "unknown"]
_STATE_VALUE = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "unknown": 0.0}

# The scoring checks. Every one traces to a rule that already exists in
# brand/principios-video.md or in the active persona — none was invented for the
# dashboard, so the score can't drift away from the doc it claims to enforce.
#
# `blocking` matters more than the score: the doc declares the theme filter
# (#9/#10/#11) *eliminatory* — "sim nas três ou não grava". A pure percentage
# would let a 65% idea read as "almost good" and quietly turn that rule into
# decoration, so a failed blocking check rejects the idea regardless of score.
IDEA_CHECKS = [
    {
        "key": "scene",
        "label": "Cena real",
        "rule": "#4 · persona",
        "blocking": False,
        "derived": False,
        "help": (
            "Existe uma história marcante do Lucas pra sustentar? "
            "Sem cena não é ideia, é tese."
        ),
    },
    {
        "key": "demand",
        "label": "Demanda",
        "rule": "#9",
        "blocking": True,
        "derived": False,
        "help": (
            "Apetite comprovado: trend em alta OU vídeo do mesmo tópico com boa "
            "tração (medir com integrations/youtube_search). Não vale "
            "'eu acho interessante'."
        ),
    },
    {
        "key": "angle",
        "label": "Ângulo",
        "rule": "#10",
        "blocking": True,
        "derived": False,
        "help": (
            "Escreva numa linha a versão óbvia deste vídeo. Se a nossa é igual, "
            "não tem ângulo — o ângulo é a distância entre as duas."
        ),
    },
    {
        "key": "value",
        "label": "Valor imediato",
        "rule": "#11",
        "blocking": True,
        "derived": False,
        "help": (
            "Nomeie em uma frase o que muda pra pessoa antes do dia acabar. "
            "Se não dá pra nomear, não tem valor — tem só assunto."
        ),
    },
    {
        "key": "facts",
        "label": "Fato verificado",
        "rule": "restrições de fato",
        "blocking": True,
        # Derivado de `trustworthy` em vez de mantido à mão: os dois significam a
        # mesma coisa, e duas fontes pro mesmo fato divergem com o tempo.
        "derived": True,
        "help": (
            "Versículos, números e citações conferidos. Espelha o campo "
            "`trustworthy` — pendência aqui bloqueia o roteiro."
        ),
    },
]

_CHECKS_BY_KEY = {c["key"]: c for c in IDEA_CHECKS}


def score_idea(idea: Idea) -> dict:
    """Nota + veredito de gate de uma ideia.

    O gate não é o score: um check bloqueante reprovado rejeita a ideia mesmo com
    nota alta, e nenhum check avaliado devolve `unassessed` em vez de `rejected` —
    "não sei" e "não presta" são coisas diferentes e a UI precisa distingui-las.
    """
    stored = idea.checks or {}
    resolved, total = [], 0.0

    for definition in IDEA_CHECKS:
        key = definition["key"]
        entry = stored.get(key) or {}
        note = entry.get("note")

        if definition["derived"] and key == "facts":
            state = "pass" if idea.trustworthy else "fail"
            note = note or (idea.fact_check or None)
        else:
            state = entry.get("state") or "unknown"
            if state not in _STATE_VALUE:
                state = "unknown"

        total += _STATE_VALUE[state]
        resolved.append({**definition, "state": state, "note": note})

    score = round(100 * total / len(IDEA_CHECKS))
    blocking_failed = [c["key"] for c in resolved if c["blocking"] and c["state"] == "fail"]
    unknown = [c["key"] for c in resolved if c["state"] == "unknown"]

    if blocking_failed:
        gate = "rejected"
    elif unknown:
        gate = "unassessed"
    elif any(c["blocking"] and c["state"] == "partial" for c in resolved):
        gate = "at_risk"
    else:
        gate = "approved"

    return {
        "score": score,
        "gate": gate,
        "blocking_failed": blocking_failed,
        "unknown": unknown,
        "checks": resolved,
    }

# Hub-and-spoke, per labs/docs/series-map.html: one long episode is the product
# (8–15min, Sunday, never under 8min — mid-roll unlocks at 8min and long-form RPM
# is ~27x Shorts in Brazil), and each episode yields 2–3 cuts (Tue/Fri, discovery)
# plus one podcast track. `short` counts 2 as the floor; 3 is ideal, not required.
WEEKLY_TARGET = {"episode": 1, "short": 2, "podcast": 1}

# Week 1 of the 26-week plan. Monday-anchored, and it reproduces the doc's own
# numbering: 2/ago falls in week 2 and 20/set in week 9, matching "Série 1 ·
# sem 2–9". Overridable per request so the view survives the next semester.
PLAN_START = date(2026, 7, 20)


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
    user = (
        db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user with email {email}",
        )
    return user.id


# --- Ideas ---


def _serialize_idea(idea: Idea, video_count: int | None = None) -> dict:
    scored = score_idea(idea)
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
        "score": scored["score"],
        "gate": scored["gate"],
        "checks": scored["checks"],
        "blocking_failed": scored["blocking_failed"],
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
        checks=data.get("checks") or {},
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
            checks=item.get("checks") or {},
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
        if value is None:
            continue
        if field == "checks":
            # MERGE, não substituição: a UI manda apenas o check que foi tocado,
            # então trocar o dict inteiro apagaria os vereditos dos outros quatro.
            # Merge é por chave e raso de propósito — cada check é {state, note},
            # e mandar só `state` preserva a `note` que já estava lá.
            merged = dict(idea.checks or {})
            for key, patch in (value or {}).items():
                if key not in _CHECKS_BY_KEY:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Check desconhecido: '{key}'. "
                            f"Válidos: {', '.join(_CHECKS_BY_KEY)}"
                        ),
                    )
                if _CHECKS_BY_KEY[key]["derived"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"O check '{key}' é derivado e não se edita direto — "
                            "mude o campo que ele espelha (trustworthy)."
                        ),
                    )
                state = (patch or {}).get("state")
                if state is not None and state not in CHECK_STATES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Estado inválido '{state}'. Válidos: {', '.join(CHECK_STATES)}",
                    )
                entry = dict(merged.get(key) or {})
                if state is not None:
                    entry["state"] = state
                if "note" in (patch or {}):
                    entry["note"] = patch["note"]
                merged[key] = entry
            idea.checks = merged
        else:
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
        # Defaults to the episode: the long piece is the product, and cuts are
        # created from it afterwards rather than scheduled independently.
        format=data.get("format") or ("episode" if idea.format == "video" else idea.format) or "episode",
        series=data.get("series"),
        episode_number=data.get("episode_number"),
        publish_date=data.get("publish_date"),
        status="idea",
    )
    db.add(video)
    idea.status = "promoted"
    db.commit()
    db.refresh(video)
    return _serialize_video(video, 0, 0)


# --- Videos ---


def _serialize_video(
    video: Video,
    script_count: int | None = None,
    derivative_count: int | None = None,
) -> dict:
    return {
        "id": video.id,
        "idea_id": video.idea_id,
        "idea_title": video.idea.title if video.idea else None,
        "parent_id": video.parent_id,
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
        "derivative_count": (
            derivative_count if derivative_count is not None else len(video.derivatives)
        ),
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


def list_videos(
    db: Session,
    user_id: UUID,
    status_filter: str | None = None,
    format_filter: str | None = None,
) -> list[dict]:
    counts = dict(
        db.query(VideoScript.video_id, func.count(VideoScript.id))
        .join(Video, Video.id == VideoScript.video_id)
        .filter(Video.user_id == user_id)
        .group_by(VideoScript.video_id)
        .all()
    )
    derivatives = dict(
        db.query(Video.parent_id, func.count(Video.id))
        .filter(Video.user_id == user_id, Video.parent_id.isnot(None))
        .group_by(Video.parent_id)
        .all()
    )
    query = db.query(Video).filter(Video.user_id == user_id)
    if status_filter:
        query = query.filter(Video.status == status_filter)
    if format_filter:
        query = query.filter(Video.format == format_filter)
    # Undated rows sort last: a calendar reads forwards, and "not scheduled yet"
    # is the tail, not the head.
    videos = query.order_by(Video.publish_date.asc().nullslast(), Video.created_at.desc()).all()
    return [
        _serialize_video(v, counts.get(v.id, 0), derivatives.get(v.id, 0)) for v in videos
    ]


def get_video(db: Session, user_id: UUID, video_id: UUID) -> dict:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    payload = _serialize_video(video)
    payload["scripts"] = [_serialize_script(s) for s in video.scripts]
    payload["derivatives"] = [_serialize_video(d, None, 0) for d in video.derivatives]
    return payload


def get_video_derivatives(db: Session, user_id: UUID, video_id: UUID) -> list[dict]:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return [_serialize_video(d, None, 0) for d in video.derivatives]


def create_derivative(db: Session, user_id: UUID, parent_id: UUID, data: dict) -> dict:
    """Create a cut or podcast hanging off an episode.

    Refuses to hang a derivative off another derivative: the model is one level
    deep (episode → cuts/podcast), and a cut of a cut is not a thing.
    """
    parent = db.query(Video).filter(Video.id == parent_id, Video.user_id == user_id).first()
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    if parent.parent_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Derivatives hang off an episode, not off another derivative",
        )

    fmt = data.get("format") or "short"
    if fmt == "episode":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An episode cannot derive from another episode",
        )

    video = Video(
        user_id=user_id,
        parent_id=parent.id,
        # Derivatives inherit the episode's idea, keyword and series: they are the
        # same piece of content in another shape, and splitting the keyword would
        # break principle #6.
        idea_id=parent.idea_id,
        title=data.get("title") or f"{parent.title} — {fmt}",
        slug=_slugify(data.get("title") or f"{parent.slug or parent.title}-{fmt}"),
        keyword=data.get("keyword") or parent.keyword,
        format=fmt,
        series=parent.series,
        episode_number=parent.episode_number,
        publish_date=data.get("publish_date"),
        status=data.get("status") or "idea",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return _serialize_video(video, 0, 0)


def cadence(
    db: Session,
    user_id: UUID,
    weeks: int = 6,
    start: date | None = None,
    plan_start: date | None = None,
) -> list[dict]:
    """What is scheduled for the coming weeks versus what the plan asks for.

    The point is the *gaps*: a table shows what exists, and what creates urgency
    is seeing an empty week. Weeks run Monday→Sunday, which puts the episode's
    Sunday slot at the end of its own week.
    """
    plan_start = plan_start or PLAN_START
    plan_monday = plan_start - timedelta(days=plan_start.weekday())

    anchor = start or date.today()
    first_monday = anchor - timedelta(days=anchor.weekday())
    last_sunday = first_monday + timedelta(days=weeks * 7 - 1)

    rows = (
        db.query(Video)
        .filter(
            Video.user_id == user_id,
            Video.publish_date.isnot(None),
            Video.publish_date >= first_monday,
            Video.publish_date <= last_sunday,
        )
        .all()
    )

    buckets: dict[date, list[Video]] = {}
    for video in rows:
        monday = video.publish_date - timedelta(days=video.publish_date.weekday())
        buckets.setdefault(monday, []).append(video)

    result = []
    for index in range(weeks):
        monday = first_monday + timedelta(days=index * 7)
        sunday = monday + timedelta(days=6)
        in_week = buckets.get(monday, [])

        counts = {fmt: 0 for fmt in WEEKLY_TARGET}
        for video in in_week:
            if video.format in counts:
                counts[video.format] += 1

        missing = {
            fmt: max(0, target - counts[fmt]) for fmt, target in WEEKLY_TARGET.items()
        }
        total_missing = sum(missing.values())
        if not in_week:
            state = "empty"
        elif total_missing == 0:
            state = "complete"
        else:
            state = "partial"

        result.append(
            {
                "week_number": (monday - plan_monday).days // 7 + 1,
                "starts_on": monday,
                "ends_on": sunday,
                "is_current": monday <= date.today() <= sunday,
                "counts": counts,
                "target": dict(WEEKLY_TARGET),
                "missing": missing,
                "state": state,
                # Whatever series the scheduled pieces belong to — read off the
                # rows rather than from a hardcoded calendar, so this cannot drift
                # away from the plan doc.
                "series": sorted({v.series for v in in_week if v.series}),
                # Episódios da semana, por número. `week_number` conta as 26
                # semanas do plano (sem 1 = 20/jul, a de carga), então quem lê
                # "ep1 na sem 2" pode achar que perdeu uma semana. Mostrar o
                # episódio resolve a ambiguidade sem mexer na numeração do plano,
                # que é a que o Lucas usa pra planejar infoproduto e livro.
                "episodes": sorted(
                    v.episode_number
                    for v in in_week
                    if v.format == "episode" and v.episode_number is not None
                ),
                "video_ids": [v.id for v in in_week],
            }
        )
    return result


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
    return _serialize_video(video, 0, 0)


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
