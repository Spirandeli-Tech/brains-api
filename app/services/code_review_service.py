"""Business logic for the Code Review module.

The API is the control plane (stores runs/steps, serves the UI). The host
runner is the execution plane (claims queued runs, executes steps, patches
status back). No credential is stored here — only references.
"""
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.models.code_review_run import CodeReviewRun
from app.models.code_review_step import CodeReviewStep

STEP_CATALOG: list[dict] = [
    {"kind": "review_draft", "sensitive": False},
    {"kind": "post_review", "sensitive": False},
]

_KIND_ORDER = {entry["kind"]: i for i, entry in enumerate(STEP_CATALOG)}

ACTIVE_RUN_STATUSES = ("queued", "running", "awaiting_approval")
TERMINAL_RUN_STATUSES = ("done", "failed", "cancelled")


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
        "ticket_key": run.ticket_key,
        "instructions": run.instructions,
        "status": run.status,
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
) -> CodeReviewRun:
    derived_pr_number = pr_number_from_url(pr_url)
    derived_ticket_key = ticket_key or ticket_key_from_url(pr_url)

    run = CodeReviewRun(
        created_by_user_id=user_id,
        connection_id=connection_id,
        pr_url=pr_url,
        pr_number=derived_pr_number,
        repo_name=repo_name or None,
        ticket_key=derived_ticket_key,
        instructions=(instructions.strip() if instructions and instructions.strip() else None),
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
    if patch.get("status") in TERMINAL_RUN_STATUSES:
        run.claimed_by = None
        run.claimed_at = None
    db.commit()
    db.refresh(run)
    return run
