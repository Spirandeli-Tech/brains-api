"""Runner overview: a single truthful view of what the (serial) runner is doing
right now and what is waiting behind it, plus per-runner liveness.

The runner processes one job at a time across five run tables, so at any moment
at most one row is `running`. We normalize all five into a common QueueItem
shape so the UI can render one "current job" + one queue, matching how the
runner actually behaves.
"""
from datetime import datetime, timedelta

from sqlalchemy import nullslast
from sqlalchemy.orm import Session

from app.models.address_pr_run import AddressPrRun
from app.models.automation import Automation
from app.models.automation_run import AutomationRun
from app.models.code_review_run import CodeReviewRun
from app.models.implementation_run import ImplementationRun
from app.models.planner_run import PlannerRun
from app.models.runner_heartbeat import RunnerHeartbeat


def record_heartbeat(db: Session, data: dict) -> None:
    runner_id = data["runner_id"]
    now = datetime.utcnow()
    hb = db.query(RunnerHeartbeat).filter(RunnerHeartbeat.runner_id == runner_id).first()
    if hb is None:
        hb = RunnerHeartbeat(runner_id=runner_id, created_at=now)
        db.add(hb)
    hb.last_seen_at = now
    hb.poll_interval = data.get("poll_interval")
    hb.dry_run = data.get("dry_run")
    hb.version = data.get("version")
    db.commit()


def _online_threshold_seconds(poll_interval: str | None) -> float:
    try:
        poll = float(poll_interval) if poll_interval else 4.0
    except (TypeError, ValueError):
        poll = 4.0
    # A missed poll or two is normal (a long job blocks the loop while it runs);
    # only flag offline once several intervals — and at least 30s — have elapsed.
    return max(30.0, poll * 6)


def _conn_name(run) -> str | None:
    conn = getattr(run, "connection", None)
    return getattr(conn, "display_name", None) if conn else None


def _automation_path(run: AutomationRun, auto: Automation) -> str:
    """The automation detail screen, anchored at this run — that's where the log
    for an automation lives. Other kinds have no per-run log screen yet."""
    return f"/automations/{auto.id}?run={run.id}"


def _automation_item(run: AutomationRun, auto: Automation, now: datetime) -> dict:
    due_at = None
    display = "running"
    if run.status != "running":
        due_at = datetime.combine(run.scheduled_for, auto.time_of_day) if auto.time_of_day else None
        if run.is_manual or due_at is None or due_at <= now:
            display = "queued"
        else:
            display = "waiting"
    return {
        "kind": "automation",
        "id": str(run.id),
        "title": auto.skill or auto.name,
        "subtitle": auto.name,
        "connection_name": auto.connection_name,
        "display_status": display,
        "is_manual": run.is_manual,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "due_at": due_at,
        "error": run.error,
        "url_path": _automation_path(run, auto),
        "can_cancel": display != "running",
    }


def _impl_item(run: ImplementationRun) -> dict:
    title = run.ticket_key or run.ticket_summary or "Implementation"
    return {
        "kind": "implementation",
        "id": str(run.id),
        "title": title,
        "subtitle": run.repo_name,
        "connection_name": _conn_name(run),
        "display_status": "running" if run.status == "running" else "queued",
        "created_at": run.created_at,
        "started_at": run.claimed_at,
        "error": run.error,
        "can_cancel": run.status != "running",
    }


def _pr_item(run, kind: str) -> dict:
    title = f"PR #{run.pr_number}" if run.pr_number else (run.pr_url or kind)
    status = "running" if run.status == "running" else (
        "awaiting_approval" if run.status == "awaiting_approval" else "queued"
    )
    return {
        "kind": kind,
        "id": str(run.id),
        "title": title,
        "subtitle": run.repo_name,
        "connection_name": _conn_name(run),
        "display_status": status,
        "created_at": run.created_at,
        "started_at": run.claimed_at,
        "error": run.error,
        "can_cancel": run.status != "running",
    }


def _planner_item(run: PlannerRun) -> dict:
    return {
        "kind": "planner",
        "id": str(run.id),
        "title": f"Planner {run.plan_date}",
        "subtitle": None,
        "connection_name": None,
        "display_status": "running" if run.status == "running" else "queued",
        "created_at": run.created_at,
        "started_at": run.claimed_at,
        "error": run.error,
    }


# Statuses that mean a run is done (as opposed to alive in the pipeline). Listed
# broadly; a table that never uses one of these simply won't match it.
_TERMINAL_STATUSES = ("done", "failed", "cancelled")
RECENT_LIMIT = 12


def _duration_seconds(start, end) -> float | None:
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def _recent_automation(run: AutomationRun, auto: Automation) -> dict:
    return {
        "kind": "automation",
        "id": str(run.id),
        "title": auto.skill or auto.name,
        "subtitle": auto.name,
        "connection_name": auto.connection_name,
        "status": run.status,
        "finished_at": run.finished_at,
        "duration_seconds": _duration_seconds(run.started_at, run.finished_at),
        "error": run.error,
        "url_path": _automation_path(run, auto),
    }


def _recent_impl(run: ImplementationRun) -> dict:
    return {
        "kind": "implementation",
        "id": str(run.id),
        "title": run.ticket_key or run.ticket_summary or "Implementation",
        "subtitle": run.repo_name,
        "connection_name": _conn_name(run),
        "status": run.status,
        "finished_at": run.updated_at,
        "duration_seconds": _duration_seconds(run.claimed_at, run.updated_at),
        "error": run.error,
    }


def _recent_pr(run, kind: str) -> dict:
    return {
        "kind": kind,
        "id": str(run.id),
        "title": f"PR #{run.pr_number}" if run.pr_number else (run.pr_url or kind),
        "subtitle": run.repo_name,
        "connection_name": _conn_name(run),
        "status": run.status,
        "finished_at": run.updated_at,
        "duration_seconds": _duration_seconds(run.claimed_at, run.updated_at),
        "error": run.error,
    }


def _recent_planner(run: PlannerRun) -> dict:
    return {
        "kind": "planner",
        "id": str(run.id),
        "title": f"Planner {run.plan_date}",
        "subtitle": None,
        "connection_name": None,
        "status": run.status,
        "finished_at": run.updated_at,
        "duration_seconds": _duration_seconds(run.claimed_at, run.updated_at),
        "error": run.error,
    }


def _build_recent(db: Session) -> list[dict]:
    """The most recently finished runs across all five tables, newest first.

    Each table is queried for its terminal rows ordered by finish time and
    capped at RECENT_LIMIT, then merged and re-capped — so the section is bounded
    regardless of how much history sits in any single table.
    """
    recent: list[dict] = []

    for run, auto in (
        db.query(AutomationRun, Automation)
        .join(Automation, Automation.id == AutomationRun.automation_id)
        .filter(AutomationRun.status.in_(_TERMINAL_STATUSES))
        .order_by(nullslast(AutomationRun.finished_at.desc()))
        .limit(RECENT_LIMIT)
        .all()
    ):
        recent.append(_recent_automation(run, auto))

    for run in (
        db.query(ImplementationRun)
        .filter(ImplementationRun.status.in_(_TERMINAL_STATUSES))
        .order_by(nullslast(ImplementationRun.updated_at.desc()))
        .limit(RECENT_LIMIT)
        .all()
    ):
        recent.append(_recent_impl(run))

    for run in (
        db.query(CodeReviewRun)
        .filter(CodeReviewRun.status.in_(_TERMINAL_STATUSES))
        .order_by(nullslast(CodeReviewRun.updated_at.desc()))
        .limit(RECENT_LIMIT)
        .all()
    ):
        recent.append(_recent_pr(run, "code_review"))

    for run in (
        db.query(AddressPrRun)
        .filter(AddressPrRun.status.in_(_TERMINAL_STATUSES))
        .order_by(nullslast(AddressPrRun.updated_at.desc()))
        .limit(RECENT_LIMIT)
        .all()
    ):
        recent.append(_recent_pr(run, "address_pr"))

    for run in (
        db.query(PlannerRun)
        .filter(PlannerRun.status.in_(_TERMINAL_STATUSES))
        .order_by(nullslast(PlannerRun.updated_at.desc()))
        .limit(RECENT_LIMIT)
        .all()
    ):
        recent.append(_recent_planner(run))

    recent.sort(key=lambda i: i.get("finished_at") or datetime.min, reverse=True)
    return recent[:RECENT_LIMIT]


def build_overview(db: Session) -> dict:
    now = datetime.utcnow()

    # --- Runners liveness ---
    runners = []
    for hb in db.query(RunnerHeartbeat).all():
        gap = (now - hb.last_seen_at).total_seconds()
        runners.append({
            "runner_id": hb.runner_id,
            "last_seen_at": hb.last_seen_at,
            "seconds_since_last_seen": gap,
            "online": gap <= _online_threshold_seconds(hb.poll_interval),
            "poll_interval": hb.poll_interval,
            "dry_run": hb.dry_run,
            "version": hb.version,
        })
    runners.sort(key=lambda r: r["runner_id"])

    items: list[dict] = []

    # Automations (join automation for skill/name/connection/time_of_day)
    auto_rows = (
        db.query(AutomationRun, Automation)
        .join(Automation, Automation.id == AutomationRun.automation_id)
        .filter(AutomationRun.status.in_(["running", "pending"]))
        .all()
    )
    for run, auto in auto_rows:
        items.append(_automation_item(run, auto, now))

    for run in db.query(ImplementationRun).filter(
        ImplementationRun.status.in_(["running", "queued"])
    ).all():
        items.append(_impl_item(run))

    for run in db.query(CodeReviewRun).filter(
        CodeReviewRun.status.in_(["running", "queued"])
    ).all():
        items.append(_pr_item(run, "code_review"))

    for run in db.query(AddressPrRun).filter(
        AddressPrRun.status.in_(["running", "queued", "awaiting_approval"])
    ).all():
        items.append(_pr_item(run, "address_pr"))

    for run in db.query(PlannerRun).filter(
        PlannerRun.status.in_(["running", "queued"])
    ).all():
        items.append(_planner_item(run))

    current = [i for i in items if i["display_status"] == "running"]
    queued = [i for i in items if i["display_status"] != "running"]

    # Queue order that mirrors reality: due items first (waiting ones sink to the
    # bottom), then oldest-created first — the tiebreak every claim query uses.
    def _sort_key(i: dict):
        waiting = i["display_status"] == "waiting"
        created = i.get("created_at") or now
        return (waiting, created)

    queued.sort(key=_sort_key)
    current.sort(key=lambda i: i.get("started_at") or now)

    return {
        "now": now,
        "runners": runners,
        "current": current,
        "queued": queued,
        "recent": _build_recent(db),
    }
