from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.automation import Automation
from app.models.automation_run import AutomationRun


def _parse_time(time_str: str | None) -> time:
    if not time_str:
        return time(8, 0)
    parts = time_str.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(h, m)


def _serialize_automation(automation: Automation, recent_runs_limit: int = 5) -> dict:
    runs = automation.runs[:recent_runs_limit]
    return {
        "id": automation.id,
        "name": automation.name,
        "skill": automation.skill,
        "connection_name": automation.connection_name,
        "work_dir": automation.work_dir,
        "frequency": automation.frequency,
        "day_of_week": automation.day_of_week,
        "day_of_month": automation.day_of_month,
        "time_of_day": automation.time_of_day.strftime("%H:%M:%S") if automation.time_of_day else "08:00:00",
        "enabled": automation.enabled,
        "created_at": automation.created_at,
        "updated_at": automation.updated_at,
        "recent_runs": [
            {
                "id": r.id,
                "scheduled_for": r.scheduled_for,
                "status": r.status,
                "log": r.log,
                "error": r.error,
                "claimed_by": r.claimed_by,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "created_at": r.created_at,
            }
            for r in runs
        ],
    }


def list_automations(db: Session, user_id: UUID) -> list[dict]:
    automations = (
        db.query(Automation)
        .filter(Automation.user_id == user_id)
        .order_by(Automation.created_at.desc())
        .all()
    )
    return [_serialize_automation(a) for a in automations]


def create_automation(db: Session, user_id: UUID, data: dict) -> dict:
    time_of_day = _parse_time(data.get("time_of_day"))
    automation = Automation(
        user_id=user_id,
        name=data["name"],
        skill=data["skill"],
        connection_name=data.get("connection_name"),
        work_dir=data.get("work_dir"),
        frequency=data["frequency"],
        day_of_week=data.get("day_of_week"),
        day_of_month=data.get("day_of_month"),
        time_of_day=time_of_day,
        enabled=True,
    )
    db.add(automation)
    db.commit()
    db.refresh(automation)
    return _serialize_automation(automation)


def get_automation(db: Session, automation_id: UUID) -> Automation | None:
    return db.query(Automation).filter(Automation.id == automation_id).first()


def update_automation(db: Session, automation: Automation, data: dict) -> dict:
    for field in ("name", "skill", "connection_name", "work_dir", "frequency", "day_of_week", "day_of_month", "enabled"):
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


def claim_next_automation_run(db: Session, runner_id: str) -> dict | None:
    stmt = (
        select(AutomationRun)
        .join(Automation)
        .where(
            AutomationRun.status == "pending",
            Automation.enabled.is_(True),
        )
        .order_by(AutomationRun.scheduled_for.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    run = db.execute(stmt).scalars().first()
    if run is None:
        return None

    run.status = "running"
    run.claimed_by = runner_id
    run.started_at = datetime.utcnow()
    db.commit()
    db.refresh(run)

    automation = run.automation
    return {
        "id": run.id,
        "automation_id": run.automation_id,
        "skill": automation.skill,
        "connection_name": automation.connection_name,
        "work_dir": automation.work_dir,
        "scheduled_for": run.scheduled_for,
    }


def update_automation_run(db: Session, run_id: UUID, data: dict) -> dict | None:
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id).first()
    if run is None:
        return None

    if "status" in data and data["status"] is not None:
        run.status = data["status"]
        if data["status"] in ("done", "failed"):
            run.finished_at = datetime.utcnow()
    if "log" in data and data["log"] is not None:
        run.log = data["log"]
    if "error" in data and data["error"] is not None:
        run.error = data["error"]

    db.commit()
    db.refresh(run)
    return {
        "id": run.id,
        "automation_id": run.automation_id,
        "scheduled_for": run.scheduled_for,
        "status": run.status,
        "log": run.log,
        "error": run.error,
        "claimed_by": run.claimed_by,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
    }
