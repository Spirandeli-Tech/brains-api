import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("scheduler")


def _init_models():
    """Import all models before anything else to resolve SQLAlchemy relationships."""
    from app.models.base import SystemMeta  # noqa: F401
    from app.models.user_role import UserRole  # noqa: F401
    from app.models.user import User  # noqa: F401
    from app.models.user_preferences import UserPreferences  # noqa: F401
    from app.models.customer import Customer  # noqa: F401
    from app.models.bank_account import BankAccount  # noqa: F401
    from app.models.contract import Contract  # noqa: F401
    from app.models.contract_service import ContractService  # noqa: F401
    from app.models.invoice import Invoice  # noqa: F401
    from app.models.invoice_service import InvoiceService  # noqa: F401
    from app.models.transaction_category import TransactionCategory  # noqa: F401
    from app.models.transaction import Transaction  # noqa: F401
    from app.models.recurring_task import RecurringTask  # noqa: F401
    from app.models.task_execution import TaskExecution  # noqa: F401


_init_models()

from app.core.db import SessionLocal  # noqa: E402
from app.scheduler.materializer import materialize_pending_executions  # noqa: E402
from app.scheduler.executor import execute_pending_tasks  # noqa: E402

INTERVAL_SECONDS = 300  # 5 minutes


def run_cycle() -> None:
    db = SessionLocal()
    try:
        materialize_pending_executions(db)
        execute_pending_tasks(db)
    except Exception:
        logger.exception("Scheduler cycle failed")
    finally:
        db.close()


async def main() -> None:
    logger.info("Scheduler started (interval=%ds)", INTERVAL_SECONDS)
    run_cycle()
    while True:
        await asyncio.sleep(INTERVAL_SECONDS)
        run_cycle()


if __name__ == "__main__":
    asyncio.run(main())
