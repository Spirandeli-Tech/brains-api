"""The proactive-platform ledger.

`emit_event` is called directly from the existing pipeline services
(automation_service, code_review_service, address_pr_service,
implementation_service) at the same status-transition sites where they
already mutate a run/step — there is no shared commit hook to plug into, so
each call site adds one `PlatformEvent` row to the same transaction the
service is already committing.

`build_briefing` is the read side: it aggregates today's events plus whatever
is currently awaiting approval or proposed, for the /briefing endpoint.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.address_pr_run import AddressPrRun
from app.models.automation_run import AutomationRun
from app.models.code_review_run import CodeReviewRun
from app.models.implementation_run import ImplementationRun
from app.models.platform_event import PlatformEvent
from app.models.proposal import Proposal

SOURCE_LABELS = {
    "implementation": "Implementação",
    "code_review": "Code review",
    "address_pr": "Address PR",
    "automation": "Automação",
    "watcher": "Watcher",
    "system": "Sistema",
}


def emit_event(
    db: Session,
    *,
    source: str,
    event_type: str,
    title: str,
    summary: str | None = None,
    connection_name: str | None = None,
    ref_kind: str | None = None,
    ref_id: str | UUID | None = None,
    url_path: str | None = None,
) -> PlatformEvent:
    event = PlatformEvent(
        occurred_at=datetime.utcnow(),
        source=source,
        event_type=event_type,
        title=title,
        summary=summary,
        connection_name=connection_name,
        ref_kind=ref_kind,
        ref_id=str(ref_id) if ref_id is not None else None,
        url_path=url_path,
    )
    db.add(event)
    return event


def _event_read(event: PlatformEvent) -> dict:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at,
        "source": event.source,
        "event_type": event.event_type,
        "title": event.title,
        "summary": event.summary,
        "connection_name": event.connection_name,
        "ref_kind": event.ref_kind,
        "ref_id": event.ref_id,
        "url_path": event.url_path,
        "seen_at": event.seen_at,
    }


def _proposal_read(proposal: Proposal) -> dict:
    return {
        "id": proposal.id,
        "created_at": proposal.created_at,
        "source": proposal.source,
        "title": proposal.title,
        "description": proposal.description,
        "action_kind": proposal.action_kind,
        "action_payload": proposal.action_payload,
        "status": proposal.status,
        "result_ref": proposal.result_ref,
    }


def _awaiting_item(*, source: str, run, title: str, url_path: str, connection_name: str | None) -> dict:
    return {
        "source": source,
        "ref_id": str(run.id),
        "title": title,
        "url_path": url_path,
        "connection_name": connection_name,
    }


def _awaiting_approval_items(db: Session) -> list[dict]:
    items: list[dict] = []

    for run in db.query(CodeReviewRun).filter(CodeReviewRun.status == "awaiting_approval").all():
        conn = run.connection
        items.append(
            _awaiting_item(
                source="code_review",
                run=run,
                title=f"Review pronta: PR {run.pr_number or run.pr_url}",
                url_path="/code-review",
                connection_name=conn.display_name if conn else None,
            )
        )

    for run in db.query(AddressPrRun).filter(AddressPrRun.status == "awaiting_approval").all():
        conn = run.connection
        items.append(
            _awaiting_item(
                source="address_pr",
                run=run,
                title=f"Fixes prontos: PR {run.pr_number or run.pr_url}",
                url_path="/address-pr-comments",
                connection_name=conn.display_name if conn else None,
            )
        )

    for run in db.query(ImplementationRun).filter(ImplementationRun.status == "awaiting_approval").all():
        conn = run.connection
        items.append(
            _awaiting_item(
                source="implementation",
                run=run,
                title=f"Aprovação pendente: {run.ticket_key or run.ticket_url}",
                url_path="/implementations",
                connection_name=conn.display_name if conn else None,
            )
        )

    return items


def _in_progress_counts(db: Session) -> dict[str, int]:
    """Runs that are alive in the runner's pipeline but don't need the user's
    attention yet — as opposed to `awaiting_approval`, which does. Surfaced
    separately in the briefing so "1 awaiting you" doesn't read as "nothing
    else is happening" when a dozen runs are still queued/running.
    """
    return {
        "implementation": (
            db.query(func.count(ImplementationRun.id))
            .filter(ImplementationRun.status.in_(("queued", "running")))
            .scalar()
        ),
        "code_review": (
            db.query(func.count(CodeReviewRun.id))
            .filter(CodeReviewRun.status.in_(("queued", "running")))
            .scalar()
        ),
        "address_pr": (
            db.query(func.count(AddressPrRun.id))
            .filter(AddressPrRun.status.in_(("queued", "running")))
            .scalar()
        ),
        "automation": (
            db.query(func.count(AutomationRun.id))
            .filter(AutomationRun.status.in_(("pending", "running")))
            .scalar()
        ),
    }


def build_briefing(db: Session, target_date: date) -> dict:
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    awaiting = _awaiting_approval_items(db)

    pending_proposals = (
        db.query(Proposal)
        .filter(Proposal.status == "pending")
        .order_by(Proposal.created_at.desc())
        .all()
    )

    day_events = (
        db.query(PlatformEvent)
        .filter(PlatformEvent.occurred_at >= day_start, PlatformEvent.occurred_at < day_end)
        .order_by(PlatformEvent.occurred_at.asc())
        .all()
    )
    done_events = [e for e in day_events if e.event_type == "run_finished"]
    failed_events = [e for e in day_events if e.event_type == "run_failed"]

    unseen_count = (
        db.query(func.count(PlatformEvent.id)).filter(PlatformEvent.seen_at.is_(None)).scalar()
    )

    narrative = _build_narrative(awaiting, pending_proposals, done_events, failed_events)

    return {
        "date": target_date,
        "narrative": narrative,
        "awaiting_approval": awaiting,
        "proposals": [_proposal_read(p) for p in pending_proposals],
        "done": [_event_read(e) for e in done_events],
        "failures": [_event_read(e) for e in failed_events],
        "timeline": [_event_read(e) for e in day_events],
        "unseen_count": unseen_count,
        "in_progress": _in_progress_counts(db),
    }


def _build_narrative(
    awaiting: list[dict],
    proposals: list[Proposal],
    done_events: list[PlatformEvent],
    failed_events: list[PlatformEvent],
) -> str:
    if not awaiting and not proposals and not done_events and not failed_events:
        return "Bom dia. Nada rodou ainda hoje — tudo tranquilo por aqui."

    parts = ["Bom dia. Enquanto você esteve fora:"]
    if awaiting:
        parts.append(f"{len(awaiting)} item(ns) aguardando sua aprovação.")
    if proposals:
        parts.append(f"{len(proposals)} proposta(s) nova(s) esperando sua decisão.")
    if done_events:
        parts.append(f"{len(done_events)} execução(ões) concluída(s).")
    if failed_events:
        parts.append(f"⚠ {len(failed_events)} falha(s) — vale dar uma olhada.")
    return " ".join(parts)


def mark_all_seen(db: Session) -> None:
    (
        db.query(PlatformEvent)
        .filter(PlatformEvent.seen_at.is_(None))
        .update({"seen_at": datetime.utcnow()}, synchronize_session=False)
    )
    db.commit()
