"""Business logic for the Implementation Center.

The API is the control plane (stores runs/steps, serves the UI). The host
runner is the execution plane (claims queued runs, executes steps, patches
status back). No credential is stored here — only references.
"""
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.models.implementation_run import ImplementationRun
from app.models.implementation_step import ImplementationStep

# Canonical catalog of steps, in execution order. `sensitive` steps pause for
# user approval. Mirrors web/src/lib/clients/implementations/constants.ts (§6).
STEP_CATALOG: list[dict] = [
    {"kind": "move_to_progress", "sensitive": False},
    {"kind": "implement", "sensitive": False},
    {"kind": "open_pr", "sensitive": True},
    {"kind": "code_review", "sensitive": False},
    {"kind": "address_feedback", "sensitive": False},
    {"kind": "qa_notes", "sensitive": False},
    {"kind": "move_card", "sensitive": True},
]

_KIND_ORDER = {entry["kind"]: i for i, entry in enumerate(STEP_CATALOG)}
_KIND_SENSITIVE = {entry["kind"]: entry["sensitive"] for entry in STEP_CATALOG}

ACTIVE_RUN_STATUSES = ("queued", "running", "awaiting_approval")
TERMINAL_RUN_STATUSES = ("done", "failed", "cancelled")


def ticket_key_from_url(url: str) -> str | None:
    m = re.search(r"([A-Z][A-Z0-9]+-\d+)", url)
    return m.group(1) if m else None


def to_run_read(run: ImplementationRun) -> dict:
    """Serialize a run, denormalizing connection name/provider for the UI."""
    conn = run.connection
    return {
        "id": run.id,
        "connection_id": run.connection_id,
        "connection_name": (conn.display_name if conn else "Unknown org"),
        "provider": (conn.provider if conn else "github"),
        "ticket_url": run.ticket_url,
        "ticket_key": run.ticket_key,
        "ticket_summary": run.ticket_summary,
        "instructions": run.instructions,
        "status": run.status,
        "worktree_path": run.worktree_path,
        "branch": run.branch,
        "pr_url": run.pr_url,
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
    ticket_url: str,
    steps: list[str],
    instructions: str | None = None,
) -> ImplementationRun:
    # Keep canonical execution order regardless of the order steps arrived in.
    ordered = sorted(set(steps), key=lambda k: _KIND_ORDER.get(k, 999))

    run = ImplementationRun(
        created_by_user_id=user_id,
        connection_id=connection_id,
        ticket_url=ticket_url,
        ticket_key=ticket_key_from_url(ticket_url),
        instructions=(instructions.strip() if instructions and instructions.strip() else None),
        status="queued",
    )
    db.add(run)
    db.flush()  # assign run.id

    for position, kind in enumerate(ordered):
        db.add(
            ImplementationStep(
                run_id=run.id,
                kind=kind,
                position=position,
                sensitive=_KIND_SENSITIVE.get(kind, False),
                status="pending",
            )
        )

    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: UUID) -> ImplementationRun | None:
    return db.query(ImplementationRun).filter(ImplementationRun.id == run_id).first()


def list_runs(db: Session, user_id: UUID) -> list[ImplementationRun]:
    return (
        db.query(ImplementationRun)
        .filter(ImplementationRun.created_by_user_id == user_id)
        .order_by(ImplementationRun.created_at.desc())
        .all()
    )


def approve_step(db: Session, run: ImplementationRun, step_id: UUID) -> ImplementationRun:
    """Approve a paused (awaiting_approval) sensitive step.

    We don't execute here — we mark the step approved and reset it to pending,
    then hand control back to the runner (run -> queued). On the next claim the
    runner sees `approved=True` and executes the step instead of pausing again.
    """
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")
    if step.status != "awaiting_approval":
        raise ValueError("Step is not awaiting approval")

    step.approved = True
    step.status = "pending"
    # Hand back to the runner: the run is runnable again.
    run.status = "queued"
    run.claimed_by = None
    run.claimed_at = None
    db.commit()
    db.refresh(run)
    return run


def cancel_run(db: Session, run: ImplementationRun) -> None:
    if run.status in TERMINAL_RUN_STATUSES:
        return
    run.status = "cancelled"
    run.claimed_by = None
    run.claimed_at = None
    db.commit()


def add_discuss_message(
    db: Session, run: ImplementationRun, step_id: UUID, message: str
) -> ImplementationRun:
    """Append a user reply to a research step and re-queue for Claude to respond."""
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")
    if step.kind != "research":
        raise ValueError("Only research steps support discussion")
    if step.status != "awaiting_approval":
        raise ValueError("Step is not awaiting your input")

    step.log = (step.log or "") + f"\n\n--- You ---\n{message}"
    step.status = "pending"
    step.approved = False
    run.status = "queued"
    run.claimed_by = None
    run.claimed_at = None
    db.commit()
    db.refresh(run)
    return run


def restart_run(db: Session, run: ImplementationRun) -> ImplementationRun:
    """Reset a stuck or failed run back to queued so the runner picks it up again.

    Resets all steps to pending, clears logs and timestamps, releases any stale
    runner claim, and clears the error field.
    """
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


def _has_pending_steps(run: ImplementationRun) -> bool:
    return any(s.status in ("pending", "running") for s in run.steps)


# --- Runner-facing operations (execution plane) ---


def claim_next_run(db: Session, runner_id: str) -> ImplementationRun | None:
    """Atomically claim the oldest runnable (queued) run.

    Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple runner instances never
    grab the same run (the Postgres equivalent of the old DynamoDB atomic claim).
    """
    stmt = (
        select(ImplementationRun)
        .where(ImplementationRun.status == "queued")
        .order_by(ImplementationRun.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .options(lazyload(ImplementationRun.connection))
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
    run: ImplementationRun,
    step_id: UUID,
    status: str | None,
    log: str | None,
) -> ImplementationRun:
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
        # A sensitive step reaching awaiting_approval pauses the whole run and
        # releases the claim so it isn't stuck under a runner that moved on.
        if status == "awaiting_approval":
            run.status = "awaiting_approval"
            run.claimed_by = None
            run.claimed_at = None

    db.commit()
    db.refresh(run)
    return run


def update_run(
    db: Session,
    run: ImplementationRun,
    patch: dict,
) -> ImplementationRun:
    for field in ("status", "worktree_path", "branch", "pr_url", "error"):
        if field in patch and patch[field] is not None:
            setattr(run, field, patch[field])
    if patch.get("status") in TERMINAL_RUN_STATUSES:
        run.claimed_by = None
        run.claimed_at = None
    db.commit()
    db.refresh(run)
    return run
