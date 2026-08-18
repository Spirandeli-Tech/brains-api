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
from app.services import connection_registry
from app.services import platform_events_service as events

# Canonical catalog of steps, in execution order. `sensitive` steps pause for
# user approval. Mirrors web/src/lib/clients/implementations/constants.ts (§6).
STEP_CATALOG: list[dict] = [
    {"kind": "enrich_ticket", "sensitive": False},
    {"kind": "move_to_progress", "sensitive": False},
    {"kind": "implement", "sensitive": False},
    {"kind": "open_pr", "sensitive": True},
    {"kind": "code_review", "sensitive": False},
    {"kind": "address_feedback", "sensitive": False},
    {"kind": "qa_notes", "sensitive": True},
    {"kind": "move_card", "sensitive": True},
]

_KIND_ORDER = {entry["kind"]: i for i, entry in enumerate(STEP_CATALOG)}
_KIND_SENSITIVE = {entry["kind"]: entry["sensitive"] for entry in STEP_CATALOG}

# Kinds that operate on a single repo's worktree/branch/PR. For multi-repo runs
# (e.g. Ecointeractive, where one ticket may touch several repos) these are
# repeated once per selected repo; everything else runs once for the whole run.
PER_REPO_KINDS = {"implement", "open_pr", "code_review", "address_feedback"}

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
        "iteration_notes": run.iteration_notes,
        "claude_model": run.claude_model,
        "repo_name": run.repo_name,
        "repo_names": run.repo_names,
        "base_branch": run.base_branch,
        "cascade_stages": run.cascade_stages,
        "pr_targets": run.pr_targets,
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
                "repo_name": s.repo_name,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
            }
            for s in run.steps
        ],
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


# --- User-facing operations ---


def get_repos_for_connection(connection_name: str) -> list[dict]:
    return connection_registry.get_repos_for_connection(connection_name)


def register_repos(connection_name: str, repos: list[dict]) -> None:
    connection_registry.register_repos(connection_name, repos)


def launch_run(
    db: Session,
    user_id: UUID,
    connection_id: UUID,
    ticket_url: str,
    steps: list[str],
    instructions: str | None = None,
    repo_name: str | None = None,
    repo_names: list[str] | None = None,
    base_branch: str | None = None,
    claude_model: str | None = None,
) -> ImplementationRun:
    # Keep canonical execution order regardless of the order steps arrived in.
    ordered = sorted(set(steps), key=lambda k: _KIND_ORDER.get(k, 999))

    # Conexões autônomas (fábrica de agentes): nenhum step pausa para aprovação.
    # Governança da empresa: gates humanos são dinheiro/publicação/legal — PR em
    # repo interno não é gate (Decision Log 18/ago). Lista via env
    # AUTONOMOUS_CONNECTIONS (display names separados por vírgula).
    from app.core.config import settings
    from app.models import ProductivityConnection

    autonomous_names = {
        n.strip() for n in (settings.AUTONOMOUS_CONNECTIONS or "").split(",") if n.strip()
    }
    conn_row = db.query(ProductivityConnection).filter(
        ProductivityConnection.id == connection_id
    ).first()
    autonomous = bool(conn_row and conn_row.display_name in autonomous_names)

    run = ImplementationRun(
        created_by_user_id=user_id,
        connection_id=connection_id,
        ticket_url=ticket_url,
        ticket_key=ticket_key_from_url(ticket_url),
        instructions=(instructions.strip() if instructions and instructions.strip() else None),
        repo_name=repo_name or None,
        repo_names=repo_names or None,
        base_branch=base_branch or None,
        claude_model=claude_model or None,
        status="queued",
    )
    db.add(run)
    db.flush()  # assign run.id

    # Repo-scoped kinds (implement, open_pr, code_review, address_feedback) repeat
    # once per selected repo, in repo order; everything else runs once for the run.
    # Falls back to the singular repo_name when repo_names wasn't sent (every
    # non-multi-repo org, e.g. Beon/Cloudwork with several repos each) — without
    # this, those steps would get repo_name=None and the runner would silently
    # resolve to whichever repo happens to be first in that org's config.
    single_repo_target = [repo_name] if repo_name else [None]
    position = 0
    for kind in ordered:
        if kind in PER_REPO_KINDS:
            targets = repo_names or single_repo_target
        else:
            targets = [None]
        for target_repo in targets:
            db.add(
                ImplementationStep(
                    run_id=run.id,
                    kind=kind,
                    position=position,
                    sensitive=False if autonomous else _KIND_SENSITIVE.get(kind, False),
                    status="pending",
                    repo_name=target_repo,
                )
            )
            position += 1

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


def iterate_step(db: Session, run: ImplementationRun, step_id: UUID, notes: str) -> ImplementationRun:
    """Request another pass on a paused sensitive step.

    - open_pr: re-runs the implement step with the new notes, then regenerates the PR preview.
    - qa_notes: appends developer feedback to the step log so the runner rewrites the comment draft.
    """
    step = next((s for s in run.steps if s.id == step_id), None)
    if step is None:
        raise ValueError("Step not found")
    if step.kind not in ("open_pr", "qa_notes"):
        raise ValueError("iterate is only supported on the open_pr and qa_notes steps")
    if step.status != "awaiting_approval":
        raise ValueError("Step is not awaiting approval")

    if step.kind == "qa_notes":
        # Append feedback to the log; the runner's preview fn will incorporate it on next pass.
        existing = (step.log or "").strip()
        step.log = f"{existing}\n\n--- Feedback from developer ---\n{notes}".strip()
        step.status = "pending"
        step.approved = False
    else:
        # open_pr: accumulate notes and reset implement + open_pr.
        existing = (run.iteration_notes or "").strip()
        run.iteration_notes = f"{existing}\n\n---\n{notes}".strip() if existing else notes

        implement_step = next((s for s in run.steps if s.kind == "implement"), None)
        if implement_step:
            implement_step.status = "pending"
            implement_step.approved = False
            implement_step.log = None
            implement_step.started_at = None
            implement_step.ended_at = None

        step.status = "pending"
        step.approved = False
        step.log = None
        step.started_at = None
        step.ended_at = None

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
    # Interruptor da empresa de agentes: com a fábrica desligada, runs das
    # conexões autônomas não são assumidas (fluxos pessoais seguem normais).
    from app.services.empresa_service import empresa_pausada

    if empresa_pausada(db):
        from app.core.config import settings
        from app.models import ProductivityConnection

        autonomous = {n.strip() for n in (settings.AUTONOMOUS_CONNECTIONS or "").split(",") if n.strip()}
        if autonomous:
            stmt = stmt.where(
                ~ImplementationRun.connection_id.in_(
                    select(ProductivityConnection.id).where(
                        ProductivityConnection.display_name.in_(autonomous)
                    )
                )
            )
    stmt = (
        stmt
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
        source="implementation",
        event_type="run_started",
        title=f"Implementação iniciada: {run.ticket_key or run.ticket_url}",
        connection_name=conn.display_name if conn else None,
        ref_kind="implementation_run",
        ref_id=run.id,
        url_path="/implementations",
    )

    db.commit()
    db.refresh(run)
    return run


def claim_cancelled_for_cleanup(db: Session, runner_id: str) -> ImplementationRun | None:
    """Atomically claim a cancelled run that may still have leftover git
    worktrees, so the runner can remove them.

    Cancelling a run only flips its status — it doesn't (and can't, from the
    control plane) touch the host's git worktrees. `worktree_path` being set
    is our signal that a worktree was created for this run at some point; we
    clear it immediately (mirroring claim_next_run's SKIP LOCKED pattern) so
    concurrent runners never race to sweep the same run twice.
    """
    stmt = (
        select(ImplementationRun)
        .where(ImplementationRun.status == "cancelled")
        .where(ImplementationRun.worktree_path.isnot(None))
        .order_by(ImplementationRun.updated_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .options(lazyload(ImplementationRun.connection))
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
            conn = run.connection
            events.emit_event(
                db,
                source="implementation",
                event_type="awaiting_approval",
                title=f"Aprovação pendente ({step.kind}): {run.ticket_key or run.ticket_url}",
                notify_detail=events.build_awaiting_detail("implementation", run, step),
                connection_name=conn.display_name if conn else None,
                ref_kind="implementation_run",
                ref_id=run.id,
                url_path="/implementations",
            )

    db.commit()
    db.refresh(run)
    return run


def update_run(
    db: Session,
    run: ImplementationRun,
    patch: dict,
) -> ImplementationRun:
    for field in (
        "status", "worktree_path", "branch", "pr_url", "error", "ticket_summary",
        "cascade_stages", "pr_targets",
    ):
        if field in patch and patch[field] is not None:
            setattr(run, field, patch[field])
    if patch.get("status") in TERMINAL_RUN_STATUSES:
        run.claimed_by = None
        run.claimed_at = None
        if patch["status"] in ("done", "failed"):
            conn = run.connection
            events.emit_event(
                db,
                source="implementation",
                event_type="run_finished" if patch["status"] == "done" else "run_failed",
                title=(
                    f"Implementação concluída: {run.ticket_key or run.ticket_url}"
                    if patch["status"] == "done"
                    else f"Implementação falhou: {run.ticket_key or run.ticket_url}"
                ),
                summary=run.error,
                connection_name=conn.display_name if conn else None,
                ref_kind="implementation_run",
                ref_id=run.id,
                url_path="/implementations",
            )
    db.commit()
    db.refresh(run)
    return run
