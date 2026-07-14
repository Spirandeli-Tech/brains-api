"""Detects runs the runner died on mid-flight, so the platform never goes
silently stuck. Two failure modes:

1. A run stuck `running` with a stale claim — the runner process that held it
   crashed or was killed. We fail the run and emit an event.
2. Automation runs piling up `pending` — no runner has been polling at all
   (e.g. the host machine/runner is off). We emit a single alert per window
   instead of one per stuck run, so it doesn't spam the ledger.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.address_pr_run import AddressPrRun
from app.models.automation_run import AutomationRun
from app.models.code_review_run import CodeReviewRun
from app.models.implementation_run import ImplementationRun
from app.models.platform_event import PlatformEvent
from app.services import platform_events_service as events

STALE_RUNNING_MINUTES = 30
STALE_PENDING_MINUTES = 15

_GATED_RUN_MODELS = (
    ("code_review", "code_review_run", "/code-review", CodeReviewRun),
    ("address_pr", "address_pr_run", "/address-pr-comments", AddressPrRun),
    ("implementation", "implementation_run", "/implementations", ImplementationRun),
)


def run_watchdog(db: Session) -> None:
    now = datetime.utcnow()
    stale_running_cutoff = now - timedelta(minutes=STALE_RUNNING_MINUTES)

    for source, ref_kind, url_path, model in _GATED_RUN_MODELS:
        stale_runs = (
            db.query(model)
            .filter(model.status == "running", model.claimed_at < stale_running_cutoff)
            .all()
        )
        for run in stale_runs:
            run.status = "failed"
            run.claimed_by = None
            run.claimed_at = None
            run.error = "Runner parece ter morrido no meio do run (detectado pelo watchdog)."
            conn = run.connection
            events.emit_event(
                db,
                source=source,
                event_type="run_failed",
                title="Run travado marcado como falho",
                summary=run.error,
                connection_name=conn.display_name if conn else None,
                ref_kind=ref_kind,
                ref_id=run.id,
                url_path=url_path,
            )

    stale_automation_runs = (
        db.query(AutomationRun)
        .filter(AutomationRun.status == "running", AutomationRun.started_at < stale_running_cutoff)
        .all()
    )
    for run in stale_automation_runs:
        run.status = "failed"
        run.error = "Runner parece ter morrido no meio do run (detectado pelo watchdog)."
        run.finished_at = now
        automation = run.automation
        events.emit_event(
            db,
            source="automation",
            event_type="run_failed",
            title=f"Automação '{automation.name}' travou e foi marcada como falha",
            summary=run.error,
            connection_name=automation.connection_name,
            ref_kind="automation_run",
            ref_id=run.id,
            url_path=f"/automations/{automation.id}",
        )

    stale_pending_cutoff = now - timedelta(minutes=STALE_PENDING_MINUTES)
    stuck_pending = (
        db.query(AutomationRun)
        .filter(AutomationRun.status == "pending", AutomationRun.created_at < stale_pending_cutoff)
        .count()
    )
    if stuck_pending:
        recent_alert = (
            db.query(PlatformEvent)
            .filter(
                PlatformEvent.event_type == "watcher_alert",
                PlatformEvent.occurred_at >= stale_pending_cutoff,
            )
            .first()
        )
        if recent_alert is None:
            events.emit_event(
                db,
                source="system",
                event_type="watcher_alert",
                title="Runner parece offline",
                summary=(
                    f"{stuck_pending} automation run(s) pendente(s) há mais de "
                    f"{STALE_PENDING_MINUTES} minutos sem serem reclamados."
                ),
            )

    db.commit()
