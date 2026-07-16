"""Business logic for `planner_runs` — fase 4a of the proactive platform
(docs/features/proactive-platform/fase4a-planejadora-jira.md).

The planner is the first piece that moves the platform from "I report what
ran" (briefing) to "I suggest what to do". Once a day it reads every org's
Jira board and has Claude synthesize a PT-BR narrative + actionable
suggestions, which land as `proposals` (source="planner").

`plan_date` is unique per user, so both entry points converge on one row:
  - scheduled: materialize_planner_run() in the scheduler, at the configured hour;
  - lazy/catch-up: GET /insights, when the Mac was off at that hour.
Both call get_or_create_today() — a day is never planned twice.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import nullsfirst, select
from sqlalchemy.orm import Session

from app.models.planner_run import PlannerRun
from app.models.proposal import Proposal
from app.services import platform_events_service as events

# action_kinds the accept path can dispatch (proposals_service.accept_proposal).
# The planner mostly emits `run_skill` (e.g. /enrich-ticket); the rest are here
# so a future planner can reuse the existing pipelines too.
DISPATCHABLE_ACTION_KINDS = {
    "run_skill",
    "start_code_review",
    "start_address_pr",
    "run_automation",
}


def _serialize_run(run: PlannerRun) -> dict:
    return {
        "id": run.id,
        "plan_date": run.plan_date,
        "status": run.status,
        "narrative": run.narrative,
        "highlights": run.highlights,
        "board_summary": run.board_summary,
        "claude_cost_usd": float(run.claude_cost_usd) if run.claude_cost_usd is not None else None,
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


# --- User-facing operations ---


def get_or_create_today(db: Session, user_id: UUID, target_date: date | None = None) -> PlannerRun:
    """The idempotency point shared by the scheduled and lazy triggers.

    Relies on the (user_id, plan_date) unique constraint: if two callers race,
    one wins the insert and the other reads the winner's row back.
    """
    plan_date = target_date or date.today()
    run = (
        db.query(PlannerRun)
        .filter(PlannerRun.user_id == user_id, PlannerRun.plan_date == plan_date)
        .first()
    )
    if run is not None:
        return run

    run = PlannerRun(user_id=user_id, plan_date=plan_date, status="queued")
    db.add(run)
    try:
        db.commit()
    except Exception:
        # Lost the race on the unique constraint — read the winner's row.
        db.rollback()
        run = (
            db.query(PlannerRun)
            .filter(PlannerRun.user_id == user_id, PlannerRun.plan_date == plan_date)
            .first()
        )
        if run is None:
            raise
        return run
    db.refresh(run)
    return run


def build_insights(db: Session, user_id: UUID, target_date: date | None = None) -> dict:
    """The /insights read side: the day's run + its pending proposals."""
    plan_date = target_date or date.today()
    # For today, create-on-read (lazy trigger). For a past date, read only.
    if target_date is None or target_date == date.today():
        run = get_or_create_today(db, user_id, plan_date)
    else:
        run = (
            db.query(PlannerRun)
            .filter(PlannerRun.user_id == user_id, PlannerRun.plan_date == plan_date)
            .first()
        )
        if run is None:
            return {"date": plan_date, "run": None, "proposals": []}

    proposals = (
        db.query(Proposal)
        .filter(Proposal.plan_run_id == run.id, Proposal.status == "pending")
        .order_by(Proposal.created_at.asc())
        .all()
    )
    data = _serialize_run(run)
    return {
        "date": plan_date,
        "run": data,
        "proposals": [
            {
                "id": p.id,
                "created_at": p.created_at,
                "source": p.source,
                "title": p.title,
                "description": p.description,
                "action_kind": p.action_kind,
                "action_payload": p.action_payload,
                "status": p.status,
                "result_ref": p.result_ref,
            }
            for p in proposals
        ],
    }


# --- Runner-facing operations ---


def claim_next_planner(db: Session, runner_id: str) -> dict | None:
    """Atomically claim the next queued planner run (FOR UPDATE SKIP LOCKED),
    mirroring the other runners. The runner iterates its own config.json
    connections to know which orgs to scan, so we only hand back id + date.
    """
    now = datetime.utcnow()
    stmt = (
        select(PlannerRun)
        .where(PlannerRun.status == "queued")
        .order_by(nullsfirst(PlannerRun.created_at.asc()))
        .limit(1)
        .with_for_update(of=PlannerRun, skip_locked=True)
    )
    run = db.execute(stmt).scalars().first()
    if run is None:
        return None

    run.status = "running"
    run.claimed_by = runner_id
    run.claimed_at = now
    db.commit()
    db.refresh(run)
    return {"id": run.id, "plan_date": run.plan_date}


def report_planner(
    db: Session,
    run_id: UUID,
    *,
    narrative: str | None,
    highlights: list[dict] | None = None,
    board_summary: dict | None,
    suggestions: list[dict] | None,
    claude_cost_usd: float | None,
) -> dict | None:
    """The runner reports the finished plan: lead + highlights + per-org board
    data + actionable suggestions. Each suggestion becomes a pending `proposal`
    (source="planner") linked back to this run. Emits `plan_ready`.
    """
    run = db.query(PlannerRun).filter(PlannerRun.id == run_id).first()
    if run is None:
        return None

    run.narrative = narrative
    run.highlights = highlights
    run.board_summary = board_summary
    if claude_cost_usd is not None:
        run.claude_cost_usd = claude_cost_usd
    run.status = "done"

    created = 0
    for s in suggestions or []:
        action_kind = s.get("action_kind")
        if action_kind not in DISPATCHABLE_ACTION_KINDS:
            # Non-actionable highlights belong in board_summary/narrative, not
            # as un-acceptable proposal cards. Skip them here.
            continue
        db.add(
            Proposal(
                source="planner",
                title=s["title"],
                description=s.get("description"),
                action_kind=action_kind,
                action_payload=s.get("action_payload") or {},
                status="pending",
                plan_run_id=run.id,
            )
        )
        created += 1

    events.emit_event(
        db,
        source="planner",
        event_type="plan_ready",
        title="Seu plano do dia está pronto",
        summary=(narrative[:200] if narrative else None),
        ref_kind="planner_run",
        ref_id=run.id,
        url_path="/insights",
    )

    db.commit()
    db.refresh(run)
    return {"id": run.id, "status": run.status, "proposals_created": created}


def report_planner_error(db: Session, run_id: UUID, error: str) -> dict | None:
    run = db.query(PlannerRun).filter(PlannerRun.id == run_id).first()
    if run is None:
        return None
    run.status = "failed"
    run.error = error
    events.emit_event(
        db,
        source="planner",
        event_type="run_failed",
        title="A planejadora do dia falhou",
        summary=error[:200] if error else None,
        ref_kind="planner_run",
        ref_id=run.id,
        url_path="/insights",
    )
    db.commit()
    db.refresh(run)
    return {"id": run.id, "status": run.status}
