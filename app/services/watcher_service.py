"""Business logic for `watchers` — fase 2 of the proactive platform.

A watcher is a runner-side check (no Claude, no cost) that polls the outside
world on an interval and turns new findings into runs the existing pipelines
already know how to execute. `github_review_requested` (W1) is the first one:
it finds PRs where the user is a requested reviewer and creates a
CodeReviewRun for each new one — the pipeline's own review_draft/post_review
gate (code_review_service.py) is what pauses for human approval, so this
service has nothing extra to gate.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import nullsfirst, or_, select, text
from sqlalchemy.orm import Session

from app.models.watcher import Watcher
from app.models.watcher_sighting import WatcherSighting
from app.services import code_review_service


def _serialize_watcher(watcher: Watcher) -> dict:
    conn = watcher.connection
    return {
        "id": watcher.id,
        "kind": watcher.kind,
        "connection_id": watcher.connection_id,
        "connection_name": conn.display_name if conn else None,
        "config": watcher.config or {},
        "interval_minutes": watcher.interval_minutes,
        "enabled": watcher.enabled,
        "last_run_at": watcher.last_run_at,
        "last_status": watcher.last_status,
        "last_error": watcher.last_error,
        "created_at": watcher.created_at,
        "updated_at": watcher.updated_at,
    }


# --- User-facing operations ---


def list_watchers(db: Session, user_id: UUID) -> list[dict]:
    watchers = (
        db.query(Watcher)
        .filter(Watcher.user_id == user_id)
        .order_by(Watcher.created_at.desc())
        .all()
    )
    return [_serialize_watcher(w) for w in watchers]


def create_watcher(db: Session, user_id: UUID, data: dict) -> dict:
    watcher = Watcher(
        user_id=user_id,
        kind=data["kind"],
        connection_id=data.get("connection_id"),
        config=data.get("config") or {},
        interval_minutes=data.get("interval_minutes") or 10,
        enabled=True,
    )
    db.add(watcher)
    db.commit()
    db.refresh(watcher)
    return _serialize_watcher(watcher)


def get_watcher(db: Session, watcher_id: UUID) -> Watcher | None:
    return db.query(Watcher).filter(Watcher.id == watcher_id).first()


def update_watcher(db: Session, watcher: Watcher, data: dict) -> dict:
    for field in ("connection_id", "config", "interval_minutes", "enabled"):
        if field in data and data[field] is not None:
            setattr(watcher, field, data[field])
    watcher.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(watcher)
    return _serialize_watcher(watcher)


def delete_watcher(db: Session, watcher: Watcher) -> None:
    db.delete(watcher)
    db.commit()


# --- Runner-facing operations ---


def claim_next_watcher(db: Session, runner_id: str) -> dict | None:  # noqa: ARG001
    now = datetime.utcnow()
    # last_run_at doubles as the lease: claiming a watcher immediately advances
    # it, so a second runner tick (or this same runner before the interval
    # elapses again) won't pick it up — no separate claimed_by/status needed.
    due = text("watchers.last_run_at + watchers.interval_minutes * interval '1 minute' <= :now")
    stmt = (
        select(Watcher)
        .where(Watcher.enabled.is_(True), or_(Watcher.last_run_at.is_(None), due))
        .params(now=now)
        .order_by(nullsfirst(Watcher.last_run_at.asc()), Watcher.created_at.asc())
        .limit(1)
        .with_for_update(of=Watcher, skip_locked=True)
    )
    watcher = db.execute(stmt).scalars().first()
    if watcher is None:
        return None

    watcher.last_run_at = now
    db.commit()
    db.refresh(watcher)

    conn = watcher.connection
    return {
        "id": watcher.id,
        "kind": watcher.kind,
        "connection_id": watcher.connection_id,
        "connection_name": conn.display_name if conn else None,
        "config": watcher.config or {},
        "interval_minutes": watcher.interval_minutes,
    }


def report_watcher_tick(
    db: Session,
    watcher_id: UUID,
    sightings: list[dict],
    status: str,
    error: str | None,
) -> dict | None:
    watcher = db.query(Watcher).filter(Watcher.id == watcher_id).first()
    if watcher is None:
        return None

    watcher.last_status = status
    watcher.last_error = error

    created_run_ids: list[str] = []
    if status == "ok":
        for sighting in sightings:
            exists = (
                db.query(WatcherSighting)
                .filter(
                    WatcherSighting.watcher_id == watcher.id,
                    WatcherSighting.external_key == sighting["external_key"],
                )
                .first()
            )
            if exists is not None:
                continue

            run = None
            if watcher.kind == "github_review_requested":
                run = code_review_service.launch_run(
                    db,
                    user_id=watcher.user_id,
                    connection_id=watcher.connection_id,
                    pr_url=sighting["pr_url"],
                    repo_name=sighting.get("repo_name"),
                )
                created_run_ids.append(str(run.id))

            db.add(
                WatcherSighting(
                    watcher_id=watcher.id,
                    external_key=sighting["external_key"],
                    handled_ref=str(run.id) if run else None,
                )
            )

    db.commit()
    return {"created_run_ids": created_run_ids}
