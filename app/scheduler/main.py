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
    from app.models.automation import Automation  # noqa: F401
    from app.models.automation_run import AutomationRun  # noqa: F401
    from app.models.productivity_connection import ProductivityConnection  # noqa: F401
    from app.models.code_review_run import CodeReviewRun  # noqa: F401
    from app.models.code_review_step import CodeReviewStep  # noqa: F401
    from app.models.address_pr_run import AddressPrRun  # noqa: F401
    from app.models.address_pr_step import AddressPrStep  # noqa: F401
    from app.models.implementation_run import ImplementationRun  # noqa: F401
    from app.models.implementation_step import ImplementationStep  # noqa: F401
    from app.models.platform_event import PlatformEvent  # noqa: F401
    from app.models.proposal import Proposal  # noqa: F401


_init_models()

from app.core.db import SessionLocal  # noqa: E402
from app.scheduler.materializer import materialize_pending_executions  # noqa: E402
from app.scheduler.executor import execute_pending_tasks  # noqa: E402
from app.scheduler.automation_materializer import materialize_automation_runs  # noqa: E402
from app.scheduler.watchdog import run_watchdog  # noqa: E402

INTERVAL_SECONDS = 300  # 5 minutes


def run_cycle() -> None:
    db = SessionLocal()
    try:
        materialize_pending_executions(db)
        execute_pending_tasks(db)
        materialize_automation_runs(db)
        materialize_planner_runs(db)
        maybe_send_daily_digest(db)
        run_watchdog(db)
    except Exception:
        logger.exception("Scheduler cycle failed")
    finally:
        db.close()


def materialize_planner_runs(db) -> None:
    """Scheduled peg of the "Insights for Today" trigger (fase 4a): for each
    user who enabled the planner, once the configured UTC hour has passed and
    there's no run for today yet, create one. get_or_create_today is idempotent,
    so this races safely with the lazy trigger (GET /insights).
    """
    from datetime import datetime

    from app.models.user_preferences import UserPreferences
    from app.services import planner_service

    now_hour = datetime.utcnow().hour
    prefs = (
        db.query(UserPreferences)
        .filter(UserPreferences.planner_enabled.is_(True))
        .all()
    )
    for p in prefs:
        if now_hour >= (p.planner_hour or 7):
            planner_service.get_or_create_today(db, p.user_id)


def maybe_send_daily_digest(db) -> None:
    """Post the morning briefing to Slack once a day, at the operator's
    planner_hour (fase 3). Guarded by a `digest_sent` system event so it fires
    exactly once per UTC day regardless of how many 5-min cycles run after the
    hour, and survives a scheduler restart. No-op when Slack isn't configured.
    """
    from datetime import datetime

    from app.models.platform_event import PlatformEvent
    from app.models.user_preferences import UserPreferences
    from app.services import notifier
    from app.services import platform_events_service as events

    if not notifier.is_configured():
        return

    prefs = db.query(UserPreferences).first()
    hour = prefs.planner_hour if prefs and prefs.planner_hour is not None else 7
    now = datetime.utcnow()
    if now.hour < hour:
        return

    day_start = datetime.combine(now.date(), datetime.min.time())
    already_sent = (
        db.query(PlatformEvent.id)
        .filter(
            PlatformEvent.event_type == "digest_sent",
            PlatformEvent.occurred_at >= day_start,
        )
        .first()
    )
    if already_sent:
        return

    briefing = events.build_briefing(db, now.date())
    notifier.notify_digest(briefing)
    events.emit_event(
        db,
        source="system",
        event_type="digest_sent",
        title="Digest matinal enviado ao Slack",
    )
    db.commit()


async def main() -> None:
    logger.info("Scheduler started (interval=%ds)", INTERVAL_SECONDS)
    # Open the Slack Socket Mode connection once at startup so interactive
    # approval buttons work (no-op if SLACK_APP_TOKEN isn't set). Non-blocking.
    from app.slack.actions import start_socket_mode
    start_socket_mode()
    run_cycle()
    while True:
        await asyncio.sleep(INTERVAL_SECONDS)
        run_cycle()


if __name__ == "__main__":
    asyncio.run(main())
