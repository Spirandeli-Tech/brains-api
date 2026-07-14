"""Business logic for `proposals` — the platform suggests, the user decides.

Accepting a proposal dispatches by `action_kind` to the same run-launching
services the UI already calls directly (code_review_service.launch_run,
address_pr_service.launch_run, automation_service.trigger_manual_run). No
proposal is created automatically yet — that arrives with the watchers in
fase 2 — so today these are only exercised manually via `POST /proposals`.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.proposal import Proposal
from app.services import address_pr_service, automation_service, code_review_service


def list_proposals(db: Session, status: str | None = None) -> list[Proposal]:
    query = db.query(Proposal)
    if status:
        query = query.filter(Proposal.status == status)
    return query.order_by(Proposal.created_at.desc()).all()


def get_proposal(db: Session, proposal_id: UUID) -> Proposal | None:
    return db.query(Proposal).filter(Proposal.id == proposal_id).first()


def create_proposal(db: Session, data: dict) -> Proposal:
    proposal = Proposal(
        source=data.get("source", "manual"),
        title=data["title"],
        description=data.get("description"),
        action_kind=data["action_kind"],
        action_payload=data["action_payload"],
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def dismiss_proposal(db: Session, proposal: Proposal) -> Proposal:
    if proposal.status != "pending":
        raise ValueError("Only pending proposals can be dismissed")
    proposal.status = "dismissed"
    db.commit()
    db.refresh(proposal)
    return proposal


def accept_proposal(db: Session, proposal: Proposal, user_id: UUID) -> Proposal:
    if proposal.status != "pending":
        raise ValueError("Only pending proposals can be accepted")

    payload = proposal.action_payload or {}

    if proposal.action_kind == "start_code_review":
        run = code_review_service.launch_run(
            db,
            user_id=user_id,
            connection_id=UUID(payload["connection_id"]),
            pr_url=payload["pr_url"],
            repo_name=payload.get("repo_name"),
            ticket_key=payload.get("ticket_key"),
            instructions=payload.get("instructions"),
            claude_model=payload.get("claude_model"),
        )
        result_ref = str(run.id)
    elif proposal.action_kind == "start_address_pr":
        run = address_pr_service.launch_run(
            db,
            user_id=user_id,
            connection_id=UUID(payload["connection_id"]),
            pr_url=payload["pr_url"],
            repo_name=payload.get("repo_name"),
            ticket_key=payload.get("ticket_key"),
            instructions=payload.get("instructions"),
            claude_model=payload.get("claude_model"),
        )
        result_ref = str(run.id)
    elif proposal.action_kind == "run_automation":
        automation = automation_service.get_automation(db, UUID(payload["automation_id"]))
        if automation is None:
            raise ValueError("Automation not found")
        run = automation_service.trigger_manual_run(db, automation)
        result_ref = str(run["id"])
    else:
        raise ValueError(
            f"action_kind '{proposal.action_kind}' isn't dispatchable yet"
        )

    proposal.status = "accepted"
    proposal.result_ref = result_ref
    db.commit()
    db.refresh(proposal)
    return proposal
