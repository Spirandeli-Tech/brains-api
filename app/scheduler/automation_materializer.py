import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.automation import Automation
from app.models.automation_run import AutomationRun
from app.scheduler.materializer import _compute_due_dates

logger = logging.getLogger("scheduler.automation_materializer")


def materialize_automation_runs(db: Session) -> int:
    today = date.today()
    automations = db.query(Automation).filter(Automation.enabled.is_(True)).all()
    created_count = 0

    for automation in automations:
        last_date = (
            db.query(func.max(AutomationRun.scheduled_for))
            .filter(AutomationRun.automation_id == automation.id)
            .scalar()
        )
        start_after = last_date if last_date else automation.created_at.date() - timedelta(days=1)

        due_dates = _compute_due_dates(automation, start_after, today)
        if not due_dates:
            continue

        for d in due_dates:
            stmt = (
                pg_insert(AutomationRun)
                .values(
                    automation_id=automation.id,
                    scheduled_for=d,
                    status="pending",
                )
                .on_conflict_do_nothing(constraint="uq_automation_run_schedule")
            )
            result = db.execute(stmt)
            if result.rowcount > 0:
                created_count += 1

    db.commit()
    if created_count > 0:
        logger.info(f"Materialized {created_count} pending automation run(s)")
    return created_count
