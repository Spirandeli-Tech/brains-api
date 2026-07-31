from __future__ import annotations

import logging
from datetime import date, datetime, time
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.models.automation import Automation
from app.models.automation_run import AutomationRun
from app.services import connection_registry
from app.services import platform_events_service as events


def _parse_time(time_str: str | None) -> time:
    if not time_str:
        return time(8, 0)
    parts = time_str.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(h, m)


def _serialize_run(run: AutomationRun) -> dict:
    return {
        "id": run.id,
        "automation_id": run.automation_id,
        "scheduled_for": run.scheduled_for,
        "status": run.status,
        "is_manual": run.is_manual,
        "phase": run.phase,
        "log": run.log,
        "result_summary": run.result_summary,
        "error": run.error,
        "claimed_by": run.claimed_by,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
    }


def _serialize_automation(automation: Automation, recent_runs_limit: int = 5) -> dict:
    runs = automation.runs[:recent_runs_limit]
    return {
        "id": automation.id,
        "name": automation.name,
        "skill": automation.skill,
        "instructions": automation.instructions,
        "connection_name": automation.connection_name,
        "repo_name": automation.repo_name,
        "claude_model": automation.claude_model,
        "frequency": automation.frequency,
        "day_of_week": automation.day_of_week,
        "day_of_month": automation.day_of_month,
        "days_of_week": automation.days_of_week,
        "time_of_day": automation.time_of_day.strftime("%H:%M:%S") if automation.time_of_day else "08:00:00",
        "enabled": automation.enabled,
        "requires_approval": automation.requires_approval,
        "tags": automation.tags or [],
        "created_at": automation.created_at,
        "updated_at": automation.updated_at,
        "recent_runs": [_serialize_run(r) for r in runs],
    }


def list_available_connections() -> list[dict]:
    """Orgs (and their repos) the runner has registered from its local config.json."""
    return connection_registry.list_connections()


def list_available_skills() -> list[str]:
    """Discover slash-command skills from the host's ~/.claude, mounted read-only."""
    claude_home = Path(settings.CLAUDE_HOME_DIR)
    names: set[str] = set()

    commands_dir = claude_home / "commands"
    if commands_dir.is_dir():
        names.update(p.stem for p in commands_dir.glob("*.md"))

    skills_dir = claude_home / "skills"
    if skills_dir.is_dir():
        names.update(p.name for p in skills_dir.iterdir() if p.is_dir())

    return sorted(f"/{name}" for name in names)


def list_automations(db: Session, user_id: UUID) -> list[dict]:
    automations = (
        db.query(Automation)
        .filter(Automation.user_id == user_id, Automation.ephemeral.is_(False))
        .order_by(Automation.created_at.desc())
        .all()
    )
    return [_serialize_automation(a) for a in automations]


def create_ephemeral_run(db: Session, user_id: UUID, payload: dict) -> dict:
    """Dispatch a one-off skill run (e.g. a planner `run_skill` proposal).

    Creates a hidden, never-scheduled Automation and immediately triggers a
    manual run of it — reusing the whole automation runner path without a new
    run type. The manual run bypasses both the time gate and the enabled gate
    (see claim_next_automation_run).
    """
    automation = Automation(
        user_id=user_id,
        name=payload.get("name") or f"Planner: {payload['skill']}",
        skill=payload["skill"],
        instructions=payload.get("instructions"),
        connection_name=payload.get("connection_name"),
        repo_name=payload.get("repo_name"),
        claude_model=payload.get("claude_model"),
        frequency="manual",
        enabled=False,
        ephemeral=True,
        meta=payload.get("meta"),
    )
    db.add(automation)
    db.commit()
    db.refresh(automation)
    return trigger_manual_run(db, automation)


def create_automation(db: Session, user_id: UUID, data: dict) -> dict:
    time_of_day = _parse_time(data.get("time_of_day"))
    automation = Automation(
        user_id=user_id,
        name=data["name"],
        skill=data["skill"],
        instructions=data.get("instructions"),
        connection_name=data.get("connection_name"),
        repo_name=data.get("repo_name"),
        claude_model=data.get("claude_model"),
        frequency=data["frequency"],
        day_of_week=data.get("day_of_week"),
        day_of_month=data.get("day_of_month"),
        days_of_week=data.get("days_of_week"),
        time_of_day=time_of_day,
        enabled=True,
        requires_approval=bool(data.get("requires_approval", False)),
        tags=data.get("tags") or [],
    )
    db.add(automation)
    db.commit()
    db.refresh(automation)
    return _serialize_automation(automation)


def get_automation(db: Session, automation_id: UUID) -> Automation | None:
    return db.query(Automation).filter(Automation.id == automation_id).first()


def get_automation_run(db: Session, run_id: UUID) -> AutomationRun | None:
    return db.query(AutomationRun).filter(AutomationRun.id == run_id).first()


def update_automation(db: Session, automation: Automation, data: dict) -> dict:
    for field in ("name", "skill", "instructions", "connection_name", "repo_name", "claude_model", "frequency", "day_of_week", "day_of_month", "days_of_week", "enabled", "requires_approval", "tags"):
        if field in data and data[field] is not None:
            setattr(automation, field, data[field])
    if "enabled" in data and data["enabled"] is not None:
        automation.enabled = data["enabled"]
    if "time_of_day" in data and data["time_of_day"] is not None:
        automation.time_of_day = _parse_time(data["time_of_day"])
    automation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(automation)
    return _serialize_automation(automation)


def delete_automation(db: Session, automation: Automation) -> None:
    db.delete(automation)
    db.commit()


def trigger_manual_run(db: Session, automation: Automation) -> dict:
    run = AutomationRun(
        automation_id=automation.id,
        scheduled_for=date.today(),
        status="pending",
        is_manual=True,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _serialize_run(run)


def claim_next_automation_run(db: Session, runner_id: str) -> dict | None:
    now = datetime.utcnow()
    # scheduled_for (date) + time_of_day (UTC clock time) is a native Postgres
    # timestamp addition. Manual "Run now" runs bypass both the time gate and
    # the enabled gate: disabling an automation only stops it from firing on
    # its own schedule, it doesn't block runs the user explicitly queued.
    due = text("automation_runs.scheduled_for + automations.time_of_day <= :now")
    stmt = (
        select(AutomationRun)
        .join(Automation)
        .where(
            AutomationRun.status == "pending",
            or_(
                AutomationRun.is_manual.is_(True),
                # A phase-2 run was already approved by the user — resume it
                # regardless of the time/enabled gate (like a manual run).
                AutomationRun.phase == 2,
                and_(Automation.enabled.is_(True), due),
            ),
        )
        .params(now=now)
        .order_by(AutomationRun.scheduled_for.asc(), AutomationRun.created_at.asc())
        .limit(1)
        .with_for_update(of=AutomationRun, skip_locked=True)
    )
    run = db.execute(stmt).scalars().first()
    if run is None:
        return None

    run.status = "running"
    run.claimed_by = runner_id
    run.started_at = now

    automation = run.automation
    events.emit_event(
        db,
        source="automation",
        event_type="run_started",
        title=f"Automação '{automation.name}' iniciada",
        connection_name=automation.connection_name,
        ref_kind="automation_run",
        ref_id=run.id,
        url_path=f"/automations/{automation.id}",
    )

    db.commit()
    db.refresh(run)

    return {
        "id": run.id,
        "automation_id": run.automation_id,
        "skill": automation.skill,
        "instructions": automation.instructions,
        "connection_name": automation.connection_name,
        "repo_name": automation.repo_name,
        "claude_model": automation.claude_model,
        "scheduled_for": run.scheduled_for,
        "phase": run.phase,
        "requires_approval": automation.requires_approval,
    }


def update_automation_run(db: Session, run_id: UUID, data: dict) -> dict | None:
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id).first()
    if run is None:
        return None

    if "status" in data and data["status"] is not None:
        run.status = data["status"]
        if data["status"] in ("done", "failed"):
            run.finished_at = datetime.utcnow()
            automation = run.automation
            events.emit_event(
                db,
                source="automation",
                event_type="run_finished" if data["status"] == "done" else "run_failed",
                title=(
                    f"Automação '{automation.name}' concluída"
                    if data["status"] == "done"
                    else f"Automação '{automation.name}' falhou"
                ),
                summary=data.get("result_summary") or data.get("error"),
                connection_name=automation.connection_name,
                ref_kind="automation_run",
                ref_id=run.id,
                url_path=f"/automations/{automation.id}",
            )
        elif data["status"] == "awaiting_approval":
            # Prepare phase done, waiting for the human to approve on the board.
            # NOT finished — release the claim so the run stops being "running",
            # but leave finished_at unset, and emit the event that lights up the
            # "Aguardando você" card + Slack ping.
            run.claimed_by = None
            automation = run.automation
            events.emit_event(
                db,
                source="automation",
                event_type="awaiting_approval",
                title=f"Automação '{automation.name}' aguardando sua aprovação",
                summary=data.get("result_summary"),
                connection_name=automation.connection_name,
                ref_kind="automation_run",
                ref_id=run.id,
                url_path=f"/automations/{automation.id}",
            )
    if "log" in data and data["log"] is not None:
        run.log = data["log"]
    if "result_summary" in data and data["result_summary"] is not None:
        run.result_summary = data["result_summary"]
    if "error" in data and data["error"] is not None:
        run.error = data["error"]

    db.commit()
    db.refresh(run)

    # Two-way Slack: when an ephemeral /slack-dispatch run finishes, turn the
    # interpreted decision into a tracked pipeline + reply on the DM. Best-effort
    # — a hiccup here must not break the status patch we just committed.
    if run.status in ("done", "failed"):
        automation = run.automation
        if automation and automation.ephemeral:
            from app.slack import dispatch
            if automation.skill == dispatch.DISPATCH_SKILL:
                try:
                    dispatch.handle_dispatch_completion(db, automation, run)
                except Exception:  # noqa: BLE001
                    logger.exception("slack dispatch completion failed")

    return _serialize_run(run)


def approve_automation_run(db: Session, run: AutomationRun) -> dict:
    """Human approved a paused (awaiting_approval) run on the board.

    Re-enqueue the SAME run as phase 2: the runner will claim it again (phase-2
    runs bypass the time/enabled gate, see claim_next_automation_run) and carry
    the automation through its finish phase (e.g. publish + deploy). Mirrors the
    approve_step → run re-queue pattern of the implementation pipeline.
    """
    run.phase = 2
    run.status = "pending"
    run.claimed_by = None
    run.started_at = None
    run.error = None
    db.commit()
    db.refresh(run)
    return _serialize_run(run)
