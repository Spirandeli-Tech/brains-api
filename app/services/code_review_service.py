"""Business logic for the Code Review module.

The API is the control plane (stores runs/steps, serves the UI). The host
runner is the execution plane (claims queued runs, executes steps, patches
status back). No credential is stored here — only references.
"""
import json
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.models.code_review_run import CodeReviewRun
from app.models.code_review_step import CodeReviewStep
from app.services import platform_events_service as events

STEP_CATALOG: list[dict] = [
    {"kind": "review_draft", "sensitive": False},
    {"kind": "post_review", "sensitive": False},
]

_KIND_ORDER = {entry["kind"]: i for i, entry in enumerate(STEP_CATALOG)}

ACTIVE_RUN_STATUSES = ("queued", "running", "awaiting_approval")
TERMINAL_RUN_STATUSES = ("done", "failed", "cancelled")
# Statuses the stale-run reaper may archive. `running` is deliberately out:
# the runner is mid-step on it and patches the status back itself.
REAPABLE_RUN_STATUSES = ("queued", "awaiting_approval")

STALE_MERGED_REASON = (
    "PR já foi mergiado ou fechado — review arquivada automaticamente."
)
STALE_NOT_REQUESTED_REASON = (
    "O PR segue aberto, mas não está mais esperando você "
    "(já aprovado por você ou fora da sua lista de reviewers) — "
    "review arquivada automaticamente."
)


def pr_number_from_url(url: str) -> str | None:
    m = re.search(r"/pull(?:-requests)?/(\d+)", url)
    return m.group(1) if m else None


def ticket_key_from_url(url: str) -> str | None:
    m = re.search(r"([A-Z][A-Z0-9]+-\d+)", url)
    return m.group(1) if m else None


def to_run_read(run: CodeReviewRun) -> dict:
    conn = run.connection
    return {
        "id": run.id,
        "connection_id": run.connection_id,
        "connection_name": (conn.display_name if conn else "Unknown org"),
        "provider": (conn.provider if conn else "github"),
        "pr_url": run.pr_url,
        "pr_number": run.pr_number,
        "repo_name": run.repo_name,
        "pr_author": run.pr_author,
        "ticket_key": run.ticket_key,
        "instructions": run.instructions,
        "claude_model": run.claude_model,
        "status": run.status,
        "auto_publish": run.auto_publish,
        "review_action": run.review_action,
        "review_plan": run.review_plan,
        "error": run.error,
        "steps": [
            {
                "id": s.id,
                "kind": s.kind,
                "sensitive": s.sensitive,
                "status": s.status,
                "approved": s.approved,
                "log": s.log,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
            }
            for s in run.steps
        ],
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


# --- User-facing operations ---


def launch_run(
    db: Session,
    user_id: UUID,
    connection_id: UUID,
    pr_url: str,
    repo_name: str | None = None,
    ticket_key: str | None = None,
    instructions: str | None = None,
    claude_model: str | None = None,
    auto_publish: bool = False,
    pr_author: str | None = None,
) -> CodeReviewRun:
    derived_pr_number = pr_number_from_url(pr_url)
    derived_ticket_key = ticket_key or ticket_key_from_url(pr_url)

    run = CodeReviewRun(
        created_by_user_id=user_id,
        connection_id=connection_id,
        pr_url=pr_url,
        pr_number=derived_pr_number,
        repo_name=repo_name or None,
        pr_author=pr_author or None,
        ticket_key=derived_ticket_key,
        instructions=(instructions.strip() if instructions and instructions.strip() else None),
        claude_model=claude_model or None,
        auto_publish=auto_publish,
        status="queued",
    )
    db.add(run)
    db.flush()

    for position, entry in enumerate(STEP_CATALOG):
        db.add(
            CodeReviewStep(
                run_id=run.id,
                kind=entry["kind"],
                position=position,
                sensitive=entry["sensitive"],
                status="pending",
            )
        )

    db.commit()
    db.refresh(run)
    return run


def has_active_run_for_pr(db: Session, pr_url: str) -> bool:
    """True if a non-terminal run already exists for this PR.

    Guards against duplicate review runs for the same PR: a second watcher on
    the same repo, or the same PR resurfacing in the review-requested list
    while a prior run is still queued/running/awaiting_approval (GitHub keeps a
    team-requested PR in that list until you personally submit a review).
    """
    existing = (
        db.query(CodeReviewRun.id)
        .filter(
            CodeReviewRun.pr_url == pr_url,
            CodeReviewRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .first()
    )
    return existing is not None


def reap_stale_runs(
    db: Session,
    connection_id: UUID | None,
    scanned_repos: list[str],
    live_keys: set[str],
    open_keys: set[str] | None,
) -> list[tuple[CodeReviewRun, str]]:
    """Archive runs whose PR no longer needs a review from me.

    A review watcher opens a run when a PR shows up in the review-requested
    list, but nothing ever closed it when the PR left that list — so a PR that
    got merged the next day kept its review parked in "Awaiting approval"
    indefinitely (17 such runs had piled up by Sep/2026, 16 of them merged).

    The fix is to read each tick as a full snapshot rather than a stream. The
    watcher reports the *whole* live set for the repos it listed end to end, so
    any reapable run inside that scope and outside the live set is provably
    stale. `open_keys` only sharpens the message (merged/closed vs. still open
    but no longer mine); when it's None the generic reason is used.

    Keys are `"<repo_name>#<pr_number>"`, matching what the watcher reports.
    Runs with no repo_name or pr_number (hand-launched from a bare URL) fall
    outside every scope and are never touched. Caller commits.
    """
    if connection_id is None or not scanned_repos:
        return []

    runs = (
        db.query(CodeReviewRun)
        .filter(
            CodeReviewRun.connection_id == connection_id,
            CodeReviewRun.repo_name.in_(list(scanned_repos)),
            CodeReviewRun.status.in_(REAPABLE_RUN_STATUSES),
        )
        .all()
    )

    reaped: list[tuple[CodeReviewRun, str]] = []
    for run in runs:
        if not run.repo_name or not run.pr_number:
            continue
        key = f"{run.repo_name}#{run.pr_number}"
        if key in live_keys:
            continue
        reason = (
            STALE_MERGED_REASON
            if open_keys is not None and key not in open_keys
            else STALE_NOT_REQUESTED_REASON
        )
        run.status = "cancelled"
        run.error = reason
        run.claimed_by = None
        run.claimed_at = None
        run.updated_at = datetime.utcnow()
        reaped.append((run, reason))

    return reaped


def get_run(db: Session, run_id: UUID) -> CodeReviewRun | None:
    return db.query(CodeReviewRun).filter(CodeReviewRun.id == run_id).first()


def list_runs(db: Session, user_id: UUID) -> list[CodeReviewRun]:
    return (
        db.query(CodeReviewRun)
        .filter(CodeReviewRun.created_by_user_id == user_id)
        .order_by(CodeReviewRun.created_at.desc())
        .all()
    )


def approve_step(
    db: Session,
    run: CodeReviewRun,
    step_id: UUID,
    review_action: str | None,
    review_plan: dict | None,
) -> CodeReviewRun:
    """Approve the review_draft step after the user reviews and filters the plan.

    Unlike Implementations (which resets to pending), here we mark the step done
    immediately and persist the filtered plan — the runner then executes post_review.
    """
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")
    if step.kind != "review_draft":
        raise ValueError("Only review_draft steps can be approved via this endpoint")
    if step.status != "awaiting_approval":
        raise ValueError("Step is not awaiting approval")

    run.review_action = review_action or "comment"
    if review_plan is not None:
        run.review_plan = review_plan

    step.approved = True
    step.status = "done"
    step.ended_at = datetime.utcnow()
    run.status = "queued"
    run.claimed_by = None
    run.claimed_at = None
    db.commit()
    db.refresh(run)
    return run


def iterate_step(
    db: Session,
    run: CodeReviewRun,
    step_id: UUID,
    notes: str,
) -> CodeReviewRun:
    """Request another draft pass on review_draft with additional instructions."""
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")
    if step.kind != "review_draft":
        raise ValueError("iterate is only supported on the review_draft step")
    if step.status != "awaiting_approval":
        raise ValueError("Step is not awaiting approval")

    existing = (step.log or "").strip()
    step.log = f"{existing}\n\n--- Feedback ---\n{notes}".strip()
    step.status = "pending"
    step.approved = False
    run.status = "queued"
    run.claimed_by = None
    run.claimed_at = None
    db.commit()
    db.refresh(run)
    return run


def cancel_run(db: Session, run: CodeReviewRun) -> None:
    if run.status in TERMINAL_RUN_STATUSES:
        return
    run.status = "cancelled"
    run.claimed_by = None
    run.claimed_at = None
    db.commit()


def restart_run(db: Session, run: CodeReviewRun) -> CodeReviewRun:
    run.status = "queued"
    run.claimed_by = None
    run.claimed_at = None
    run.error = None
    for step in run.steps:
        step.status = "pending"
        step.approved = False
        step.log = None
        step.started_at = None
        step.ended_at = None
    db.commit()
    db.refresh(run)
    return run


# --- Runner-facing operations ---


def claim_next_run(db: Session, runner_id: str) -> CodeReviewRun | None:
    stmt = (
        select(CodeReviewRun)
        .where(CodeReviewRun.status == "queued")
        .order_by(CodeReviewRun.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .options(lazyload(CodeReviewRun.connection))
    )
    run = db.execute(stmt).scalars().first()
    if run is None:
        return None

    run.status = "running"
    run.claimed_by = runner_id
    run.claimed_at = datetime.utcnow()

    conn = run.connection
    events.emit_event(
        db,
        source="code_review",
        event_type="run_started",
        title=f"Review iniciado: PR {run.pr_number or run.pr_url}",
        connection_name=conn.display_name if conn else None,
        ref_kind="code_review_run",
        ref_id=run.id,
        url_path="/code-review",
    )

    db.commit()
    db.refresh(run)
    return run


def update_step(
    db: Session,
    run: CodeReviewRun,
    step_id: UUID,
    status: str | None,
    log: str | None,
) -> CodeReviewRun:
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")

    if log is not None:
        step.log = log
    if status is not None:
        step.status = status
        if status == "running" and step.started_at is None:
            step.started_at = datetime.utcnow()
        if status in ("done", "skipped", "failed"):
            step.ended_at = datetime.utcnow()
        if status == "awaiting_approval":
            run.status = "awaiting_approval"
            run.claimed_by = None
            run.claimed_at = None
            conn = run.connection
            action_value = json.dumps({"run_id": str(run.id), "step_id": str(step.id)})
            events.emit_event(
                db,
                source="code_review",
                event_type="awaiting_approval",
                title=f"Review pronta: PR {run.pr_number or run.pr_url}",
                notify_detail=events.build_awaiting_detail("code_review", run, step),
                notify_actions=[
                    {"text": "✅ Aprovar e postar", "action_id": "cr_approve",
                     "style": "primary", "value": action_value},
                    {"text": "🗑️ Descartar", "action_id": "cr_discard",
                     "style": "danger", "value": action_value},
                ],
                connection_name=conn.display_name if conn else None,
                ref_kind="code_review_run",
                ref_id=run.id,
                url_path="/code-review",
            )

    db.commit()
    db.refresh(run)
    return run


def update_run(
    db: Session,
    run: CodeReviewRun,
    patch: dict,
) -> CodeReviewRun:
    for field in ("status", "pr_number", "review_action", "review_plan", "error"):
        if field in patch and patch[field] is not None:
            setattr(run, field, patch[field])
    # `summary` is an event-only override (not a column): the runner uses it to
    # explain a run that finished without posting, e.g. a PR that closed/merged
    # before the review went out. Falls back to run.error when absent.
    event_summary = patch.get("summary") or run.error
    if patch.get("status") in TERMINAL_RUN_STATUSES:
        run.claimed_by = None
        run.claimed_at = None
        if patch["status"] in ("done", "failed"):
            conn = run.connection
            events.emit_event(
                db,
                source="code_review",
                event_type="run_finished" if patch["status"] == "done" else "run_failed",
                title=(
                    f"Review concluído: PR {run.pr_number or run.pr_url}"
                    if patch["status"] == "done"
                    else f"Review falhou: PR {run.pr_number or run.pr_url}"
                ),
                summary=event_summary,
                notify_detail=events.build_finished_detail("code_review", run),
                connection_name=conn.display_name if conn else None,
                ref_kind="code_review_run",
                ref_id=run.id,
                url_path="/code-review",
            )
    db.commit()
    db.refresh(run)
    return run
