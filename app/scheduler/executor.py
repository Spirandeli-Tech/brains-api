import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.task_execution import TaskExecution
from app.models.recurring_task import RecurringTask
from app.scheduler.handlers import TASK_HANDLERS

logger = logging.getLogger("scheduler.executor")


def execute_pending_tasks(db: Session) -> int:
    """Find all pending executions due today or earlier, and run them."""
    today = date.today()

    pending = (
        db.query(TaskExecution)
        .join(RecurringTask)
        .filter(
            TaskExecution.status == "pending",
            TaskExecution.scheduled_for <= today,
            RecurringTask.enabled.is_(True),
        )
        .order_by(TaskExecution.scheduled_for.asc())
        .all()
    )

    if not pending:
        return 0

    executed_count = 0
    for execution in pending:
        task = execution.recurring_task
        handler = TASK_HANDLERS.get(task.task_type)

        if not handler:
            logger.error(f"No handler for task_type={task.task_type}, task_id={task.id}")
            execution.status = "failed"
            execution.error_message = f"Unknown task_type: {task.task_type}"
            execution.executed_at = datetime.utcnow()
            db.commit()
            continue

        execution.status = "running"
        db.commit()

        try:
            result_id = handler.execute(db, task, execution)
            execution.status = "completed"
            execution.result_reference_id = result_id
            logger.info(
                f"Completed task_type={task.task_type}, "
                f"scheduled_for={execution.scheduled_for}, "
                f"result_id={result_id}"
            )
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            logger.exception(
                f"Failed task_type={task.task_type}, "
                f"scheduled_for={execution.scheduled_for}"
            )
        finally:
            execution.executed_at = datetime.utcnow()
            db.commit()
            executed_count += 1

    return executed_count
