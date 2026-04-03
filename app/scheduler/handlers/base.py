import uuid
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models.recurring_task import RecurringTask
from app.models.task_execution import TaskExecution


class TaskHandler(ABC):
    @abstractmethod
    def execute(
        self,
        db: Session,
        task: RecurringTask,
        execution: TaskExecution,
    ) -> uuid.UUID | None:
        """Execute the task. Return the ID of the created resource, or None."""
        ...
