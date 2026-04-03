import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.recurring_task import RecurringTask
from app.models.task_execution import TaskExecution

logger = logging.getLogger("scheduler.materializer")


def _compute_due_dates(task: RecurringTask, after: date, until: date) -> list[date]:
    """Compute all scheduled dates for a task between (after, until] inclusive of until."""
    dates: list[date] = []

    if task.frequency == "daily":
        current = after + timedelta(days=1)
        while current <= until:
            dates.append(current)
            current += timedelta(days=1)

    elif task.frequency == "weekly":
        current = after + timedelta(days=1)
        while current <= until:
            if current.weekday() == task.day_of_week:
                dates.append(current)
            current += timedelta(days=1)

    elif task.frequency == "monthly":
        import calendar
        year, month = after.year, after.month
        for _ in range(60):
            month += 1
            if month > 12:
                month = 1
                year += 1
            max_day = calendar.monthrange(year, month)[1]
            day = min(task.day_of_month, max_day)
            candidate = date(year, month, day)
            if candidate > until:
                break
            if candidate > after:
                dates.append(candidate)

    return dates


def materialize_pending_executions(db: Session) -> int:
    """For every enabled recurring task, create pending executions for missed dates up to today."""
    today = date.today()
    tasks = db.query(RecurringTask).filter(RecurringTask.enabled.is_(True)).all()
    created_count = 0

    for task in tasks:
        last_date = (
            db.query(func.max(TaskExecution.scheduled_for))
            .filter(TaskExecution.recurring_task_id == task.id)
            .scalar()
        )
        start_after = last_date if last_date else task.created_at.date() - timedelta(days=1)

        due_dates = _compute_due_dates(task, start_after, today)
        if not due_dates:
            continue

        for d in due_dates:
            stmt = (
                pg_insert(TaskExecution)
                .values(
                    recurring_task_id=task.id,
                    scheduled_for=d,
                    status="pending",
                )
                .on_conflict_do_nothing(constraint="uq_task_execution_schedule")
            )
            result = db.execute(stmt)
            if result.rowcount > 0:
                created_count += 1

    db.commit()
    if created_count > 0:
        logger.info(f"Materialized {created_count} pending execution(s)")
    return created_count
