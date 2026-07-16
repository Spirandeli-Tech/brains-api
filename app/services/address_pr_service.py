"""Business logic for the Address PR Comments module.

The API is the control plane (stores runs/steps, serves the UI). The host
runner is the execution plane (claims queued runs, checks out the PR branch
into an isolated worktree, executes steps, patches status back). No
credential is stored here — only references.
"""
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.models.address_pr_run import AddressPrRun
from app.models.address_pr_step import AddressPrStep
from app.services import platform_events_service as events

STEP_CATALOG: list[dict] = [
    {"kind": "fix_draft", "sensitive": False},
    {"kind": "commit_push", "sensitive": False},
    {"kind": "post_replies", "sensitive": False},
]

# Steps that pause for human approval after they run (as opposed to running
# straight through, like post_replies).
APPROVABLE_STEP_KINDS = ("fix_draft", "commit_push")

ACTIVE_RUN_STATUSES = ("queued", "running", "awaiting_approval")
TERMINAL_RUN_STATUSES = ("done", "failed", "cancelled")


def pr_number_from_url(url: str) -> str | None:
    m = re.search(r"/pull(?:-requests)?/(\d+)", url)
    return m.group(1) if m else None


def ticket_key_from_url(url: str) -> str | None:
    m = re.search(r"([A-Z][A-Z0-9]+-\d+)", url)
    return m.group(1) if m else None


def to_run_read(run: AddressPrRun) -> dict:
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
        "claude_model": run.claude_model,
        "status": run.status,
        "worktree_path": run.worktree_path,
        "branch": run.branch,
        "fix_plan": run.fix_plan,
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
) -> AddressPrRun:
    derived_pr_number = pr_number_from_url(pr_url)
    derived_ticket_key = ticket_key or ticket_key_from_url(pr_url)

    run = AddressPrRun(
        created_by_user_id=user_id,
        connection_id=connection_id,
        pr_url=pr_url,
        pr_number=derived_pr_number,
        repo_name=repo_name or None,
        ticket_key=derived_ticket_key,
        instructions=(instructions.strip() if instructions and instructions.strip() else None),
        claude_model=claude_model or None,
        status="queued",
    )
    db.add(run)
    db.flush()

    for position, entry in enumerate(STEP_CATALOG):
        db.add(
            AddressPrStep(
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


def get_run(db: Session, run_id: UUID) -> AddressPrRun | None:
    return db.query(AddressPrRun).filter(AddressPrRun.id == run_id).first()


def list_runs(db: Session, user_id: UUID) -> list[AddressPrRun]:
    return (
        db.query(AddressPrRun)
        .filter(AddressPrRun.created_by_user_id == user_id)
        .order_by(AddressPrRun.created_at.desc())
        .all()
    )


def has_active_run_for_pr(db: Session, pr_url: str) -> bool:
    """True if a non-terminal address-PR run already exists for this PR.

    Guards W2 (github_reviews_received): a PR can accrue several new
    reviews/comments while its fix run is still queued/running/awaiting
    approval — each is a fresh sighting, but they must all fold into the one
    open run instead of forking a second. Also dedups against a run I kicked
    off manually for the same PR.
    """
    existing = (
        db.query(AddressPrRun.id)
        .filter(
            AddressPrRun.pr_url == pr_url,
            AddressPrRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .first()
    )
    return existing is not None


def approve_step(
    db: Session,
    run: AddressPrRun,
    step_id: UUID,
    fix_plan: dict | None,
) -> AddressPrRun:
    """Approve fix_draft (gate 1: which fixes to apply) or commit_push (gate 2:
    which replies to post), after the user reviews/edits the plan.

    Marks the step done immediately and persists the updated plan — the
    runner then executes the next step (commit_push or post_replies).
    """
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")
    if step.kind not in APPROVABLE_STEP_KINDS:
        raise ValueError(f"Step kind '{step.kind}' cannot be approved via this endpoint")
    if step.status != "awaiting_approval":
        raise ValueError("Step is not awaiting approval")

    if fix_plan is not None:
        run.fix_plan = fix_plan

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
    run: AddressPrRun,
    step_id: UUID,
    notes: str,
) -> AddressPrRun:
    """Request another draft pass on fix_draft with additional instructions."""
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")
    if step.kind != "fix_draft":
        raise ValueError("iterate is only supported on the fix_draft step")
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


def cancel_run(db: Session, run: AddressPrRun) -> None:
    if run.status in TERMINAL_RUN_STATUSES:
        return
    run.status = "cancelled"
    run.claimed_by = None
    run.claimed_at = None
    db.commit()


def restart_run(db: Session, run: AddressPrRun) -> AddressPrRun:
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


def claim_next_run(db: Session, runner_id: str) -> AddressPrRun | None:
    stmt = (
        select(AddressPrRun)
        .where(AddressPrRun.status == "queued")
        .order_by(AddressPrRun.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .options(lazyload(AddressPrRun.connection))
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
        source="address_pr",
        event_type="run_started",
        title=f"Address PR iniciado: PR {run.pr_number or run.pr_url}",
        connection_name=conn.display_name if conn else None,
        ref_kind="address_pr_run",
        ref_id=run.id,
        url_path="/address-pr-comments",
    )

    db.commit()
    db.refresh(run)
    return run


def claim_cancelled_for_cleanup(db: Session, runner_id: str) -> AddressPrRun | None:
    """Atomically claim a cancelled run that may still have a leftover git
    worktree, so the runner can remove it.

    Cancelling a run only flips its status — it doesn't (and can't, from the
    control plane) touch the host's git worktree. `worktree_path` being set
    is our signal that a worktree was created for this run at some point; we
    clear it immediately (mirroring claim_next_run's SKIP LOCKED pattern) so
    concurrent runners never race to sweep the same run twice.
    """
    stmt = (
        select(AddressPrRun)
        .where(AddressPrRun.status == "cancelled")
        .where(AddressPrRun.worktree_path.isnot(None))
        .order_by(AddressPrRun.updated_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .options(lazyload(AddressPrRun.connection))
    )
    run = db.execute(stmt).scalars().first()
    if run is None:
        return None

    run.worktree_path = None
    db.commit()
    db.refresh(run)
    return run


def update_step(
    db: Session,
    run: AddressPrRun,
    step_id: UUID,
    status: str | None,
    log: str | None,
) -> AddressPrRun:
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
            events.emit_event(
                db,
                source="address_pr",
                event_type="awaiting_approval",
                title=f"Fixes prontos ({step.kind}): PR {run.pr_number or run.pr_url}",
                connection_name=conn.display_name if conn else None,
                ref_kind="address_pr_run",
                ref_id=run.id,
                url_path="/address-pr-comments",
            )

    db.commit()
    db.refresh(run)
    return run


def update_run(
    db: Session,
    run: AddressPrRun,
    patch: dict,
) -> AddressPrRun:
    for field in ("status", "pr_number", "worktree_path", "branch", "fix_plan", "error"):
        if field in patch and patch[field] is not None:
            setattr(run, field, patch[field])
    if patch.get("status") in TERMINAL_RUN_STATUSES:
        run.claimed_by = None
        run.claimed_at = None
        if patch["status"] in ("done", "failed"):
            conn = run.connection
            events.emit_event(
                db,
                source="address_pr",
                event_type="run_finished" if patch["status"] == "done" else "run_failed",
                title=(
                    f"Address PR concluído: PR {run.pr_number or run.pr_url}"
                    if patch["status"] == "done"
                    else f"Address PR falhou: PR {run.pr_number or run.pr_url}"
                ),
                summary=run.error,
                connection_name=conn.display_name if conn else None,
                ref_kind="address_pr_run",
                ref_id=run.id,
                url_path="/address-pr-comments",
            )
    db.commit()
    db.refresh(run)
    return run
