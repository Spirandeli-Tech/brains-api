"""HTTP surface for the content pipeline: ideas → videos → scripts.

Two audiences, two auth schemes — the same split every other domain here uses:
the dashboard calls the user-facing endpoints with a Firebase session, and the
labs skills (`/social-buscar-trends`, `/social-roteirizar-ideia`) call the
`/runner/*` endpoints with `X-Runner-Token`. Runner payloads name the user by
email because there is no session to infer it from and this database has several
users.
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.content import (
    CadenceWeek,
    DerivativeCreate,
    IdeaCreate,
    IdeaRead,
    IdeaTopicRead,
    IdeaUpdate,
    PromoteIdeaRequest,
    RunnerIdeaBulkCreate,
    RunnerScriptCreate,
    TopicsGenerateRead,
    TopicsUpdate,
    VideoCreate,
    VideoDetailRead,
    VideoRead,
    VideoScriptCreate,
    VideoScriptRead,
    VideoUpdate,
)
from app.services import content_service as svc

router = APIRouter(prefix="/content", tags=["content"])


def require_runner(x_runner_token: str | None = Header(default=None)) -> bool:
    if not settings.RUNNER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runner endpoints are disabled. Set RUNNER_TOKEN to enable.",
        )
    if x_runner_token != settings.RUNNER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid runner token",
        )
    return True


# --- Ideas (user-facing) ---


@router.get("/ideas", response_model=list[IdeaRead])
def list_ideas(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_ideas(db, current_user.id, status_filter)


@router.post("/ideas", response_model=IdeaRead, status_code=status.HTTP_201_CREATED)
def create_idea(
    data: IdeaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_idea(db, current_user.id, data.model_dump(exclude_unset=True))


@router.get("/ideas/{idea_id}", response_model=IdeaRead)
def get_idea(
    idea_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_idea(db, current_user.id, idea_id)


@router.patch("/ideas/{idea_id}", response_model=IdeaRead)
def update_idea(
    idea_id: UUID,
    data: IdeaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.update_idea(db, current_user.id, idea_id, data.model_dump(exclude_unset=True))


@router.delete("/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idea(
    idea_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc.delete_idea(db, current_user.id, idea_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/ideas/{idea_id}/promote",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
)
def promote_idea(
    idea_id: UUID,
    data: PromoteIdeaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.promote_idea(db, current_user.id, idea_id, data.model_dump(exclude_unset=True))


# --- Videos (user-facing) ---


@router.get("/videos", response_model=list[VideoRead])
def list_videos(
    status_filter: str | None = None,
    format_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_videos(db, current_user.id, status_filter, format_filter)


@router.get("/cadence", response_model=list[CadenceWeek])
def get_cadence(
    weeks: int = 6,
    start: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scheduled versus planned, week by week — the gaps are the point."""
    if not 1 <= weeks <= 26:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="weeks must be between 1 and 26",
        )
    return svc.cadence(db, current_user.id, weeks, start)


@router.post("/videos", response_model=VideoRead, status_code=status.HTTP_201_CREATED)
def create_video(
    data: VideoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_video(db, current_user.id, data.model_dump(exclude_unset=True))


@router.get("/videos/{video_id}", response_model=VideoDetailRead)
def get_video(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_video(db, current_user.id, video_id)


@router.patch("/videos/{video_id}", response_model=VideoRead)
def update_video(
    video_id: UUID,
    data: VideoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.update_video(db, current_user.id, video_id, data.model_dump(exclude_unset=True))


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc.delete_video(db, current_user.id, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/videos/{video_id}/derivatives", response_model=list[VideoRead])
def list_derivatives(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_video_derivatives(db, current_user.id, video_id)


@router.post(
    "/videos/{video_id}/derivatives",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
)
def create_derivative(
    video_id: UUID,
    data: DerivativeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a cut or the podcast to an episode (2–3 cuts per episode is the plan)."""
    return svc.create_derivative(db, current_user.id, video_id, data.model_dump(exclude_unset=True))


# --- Scripts (user-facing) ---


@router.get("/videos/{video_id}/scripts", response_model=list[VideoScriptRead])
def list_scripts(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_scripts(db, current_user.id, video_id)


@router.post(
    "/videos/{video_id}/scripts",
    response_model=VideoScriptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_script(
    video_id: UUID,
    data: VideoScriptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_script(db, current_user.id, video_id, data.model_dump(exclude_unset=True))


@router.delete(
    "/videos/{video_id}/scripts/{script_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_script(
    video_id: UUID,
    script_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc.delete_script(db, current_user.id, video_id, script_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/videos/{video_id}/scripts/{script_id}/topics/generate",
    response_model=TopicsGenerateRead,
)
def generate_topics(
    video_id: UUID,
    script_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drafts the cola via Gemini. Returns the draft only — nothing is saved
    until the user reviews it and calls `save_topics`."""
    return svc.generate_topics_draft(db, current_user.id, video_id, script_id)


@router.put(
    "/videos/{video_id}/scripts/{script_id}/topics",
    response_model=VideoScriptRead,
)
def save_topics(
    video_id: UUID,
    script_id: UUID,
    data: TopicsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.save_topics(db, current_user.id, video_id, script_id, data.topics_md)


# --- Runner-facing (labs skills) ---


@router.get("/runner/idea-topics", response_model=list[IdeaTopicRead])
def runner_list_idea_topics(
    user_email: str,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    """The anti-repetition memory for `/social-buscar-trends`: every idea, any
    status, in the slim shape the dedup step needs."""
    user_id = svc.resolve_user_id(db, user_email)
    return svc.list_idea_topics(db, user_id)


@router.post(
    "/runner/ideas",
    response_model=list[IdeaRead],
    status_code=status.HTTP_201_CREATED,
)
def runner_create_ideas(
    data: RunnerIdeaBulkCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    user_id = svc.resolve_user_id(db, data.user_email)
    return svc.create_ideas_bulk(
        db, user_id, [i.model_dump(exclude_unset=True) for i in data.ideas]
    )


@router.get("/runner/ideas/{idea_id}", response_model=IdeaRead)
def runner_get_idea(
    idea_id: UUID,
    user_email: str,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    user_id = svc.resolve_user_id(db, user_email)
    return svc.get_idea(db, user_id, idea_id)


@router.get("/runner/videos", response_model=list[VideoRead])
def runner_list_videos(
    user_email: str,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    user_id = svc.resolve_user_id(db, user_email)
    return svc.list_videos(db, user_id, status_filter)


@router.post(
    "/runner/videos/{video_id}/scripts",
    response_model=VideoScriptRead,
    status_code=status.HTTP_201_CREATED,
)
def runner_create_script(
    video_id: UUID,
    data: RunnerScriptCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    payload = data.model_dump(exclude_unset=True)
    user_id = svc.resolve_user_id(db, payload.pop("user_email"))
    return svc.create_script(db, user_id, video_id, payload)


@router.post(
    "/runner/ideas/{idea_id}/promote",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
)
def runner_promote_idea(
    idea_id: UUID,
    user_email: str,
    data: PromoteIdeaRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    user_id = svc.resolve_user_id(db, user_email)
    return svc.promote_idea(db, user_id, idea_id, data.model_dump(exclude_unset=True))
