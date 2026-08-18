"""Módulo Empresa — a fábrica de SaaS operada por agentes.

Três responsabilidades: o registro dos agentes (seed de fabrica/agents.yaml),
o feed de mensagens com o dispatcher (mensagem endereçada e acionável vira
AgentTask na fila do destinatário + espelho no Slack), e a fila de tasks com
claim pelo runner no padrão FOR UPDATE SKIP LOCKED — com a trava de identidade
da empresa: no máximo 1 task running por agente (paralelismo entre agentes,
nunca do mesmo agente).

Protocolo (fabrica/PROTOCOLO.md): o investidor só fala com o CEO — mensagens
user-facing são forçadas para o slug do CEO e enfileiram a skill ceo-diretriz.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, AgentMessage, AgentTask
from app.services import platform_events_service as events

CEO_SLUG = "salomao"
INVESTOR = "investidor"
DEFAULT_SKILL = "atender-mensagem"
INVESTOR_DIRECTIVE_SKILL = "ceo-diretriz"


# --- Rituais (agenda da empresa, lida de fabrica/rituais.yaml montado ro) ---

FABRICA_DIR = os.environ.get("FABRICA_DIR", "/data/fabrica")


def list_rituais() -> list[dict]:
    """Agenda + último disparo (estado gravado pelo runner). Vazio se não montado."""
    rituais_path = os.path.join(FABRICA_DIR, "rituais.yaml")
    state_path = os.path.join(FABRICA_DIR, ".rituais-state.json")
    if not os.path.exists(rituais_path):
        return []
    try:
        import json as _json

        import yaml

        rituais = (yaml.safe_load(open(rituais_path)) or {}).get("rituais", [])
        state = _json.load(open(state_path)) if os.path.exists(state_path) else {}
    except Exception:  # noqa: BLE001
        return []
    return [
        {
            "name": r.get("name"),
            "agent_slug": r.get("agent"),
            "skill": r.get("skill"),
            "weekday": r.get("weekday"),
            "day_of_month": r.get("day_of_month"),
            "time": str(r.get("time", "")),
            "last_fired": state.get(r.get("name")),
        }
        for r in rituais
        if r.get("name")
    ]


# --- Agents ---


def seed_agents(db: Session, items: list[dict]) -> int:
    """Upsert idempotente por slug — fabrica/agents.yaml é a fonte de verdade."""
    count = 0
    for item in items:
        agent = db.query(Agent).filter(Agent.slug == item["slug"]).first()
        if agent is None:
            agent = Agent(slug=item["slug"])
            db.add(agent)
        for field in ("human_name", "role", "area", "reports_to", "bio", "skills"):
            if field in item and item[field] is not None:
                setattr(agent, field, item[field])
        agent.updated_at = datetime.utcnow()
        count += 1
    db.commit()
    return count


def list_agents(db: Session) -> list[dict]:
    """Agentes + estado derivado das tasks (running/queued/custo acumulado)."""
    agents = db.query(Agent).filter(Agent.enabled.is_(True)).order_by(Agent.created_at.asc()).all()

    running = {
        t.agent_slug: t.skill
        for t in db.query(AgentTask).filter(AgentTask.status == "running").all()
    }
    queued_counts = dict(
        db.execute(
            select(AgentTask.agent_slug, func.count())
            .where(AgentTask.status == "queued")
            .group_by(AgentTask.agent_slug)
        ).all()
    )
    costs = dict(
        db.execute(
            select(AgentTask.agent_slug, func.coalesce(func.sum(AgentTask.cost_usd), 0))
            .group_by(AgentTask.agent_slug)
        ).all()
    )

    result = []
    for a in agents:
        current_skill = running.get(a.slug)
        result.append(
            {
                "id": a.id,
                "slug": a.slug,
                "human_name": a.human_name,
                "role": a.role,
                "area": a.area,
                "reports_to": a.reports_to,
                "bio": a.bio,
                "skills": a.skills or [],
                "enabled": a.enabled,
                "status": "running" if current_skill else ("queued" if queued_counts.get(a.slug) else "idle"),
                "current_skill": current_skill,
                "queued_count": int(queued_counts.get(a.slug, 0)),
                "total_cost_usd": float(costs.get(a.slug) or 0),
            }
        )
    return result


# --- Messages + dispatcher ---


def _mirror_to_slack(db: Session, message: AgentMessage) -> None:
    """Espelha a mensagem no canal da empresa via platform event (nunca levanta)."""
    to_part = f" → @{message.to_agent}" if message.to_agent else ""
    events.emit_event(
        db,
        source="empresa",
        event_type="agent_message",
        title=f"@{message.from_agent}{to_part}",
        summary=message.body[:400],
        ref_kind="agent_message",
        ref_id=message.id,
        url_path="/empresa",
    )


def create_message(
    db: Session,
    *,
    from_agent: str,
    to_agent: str | None,
    body: str,
    artifact_url: str | None = None,
    skill: str | None = None,
    enqueue: bool = True,
) -> AgentMessage:
    """Cria a mensagem e despacha: endereçada + acionável => task na fila do destinatário."""
    if to_agent is not None:
        exists = db.query(Agent).filter(Agent.slug == to_agent, Agent.enabled.is_(True)).first()
        if exists is None:
            raise ValueError(f"Agente desconhecido: {to_agent}")

    message = AgentMessage(
        from_agent=from_agent,
        to_agent=to_agent,
        body=body,
        artifact_url=artifact_url,
    )
    db.add(message)
    db.flush()

    if to_agent is not None and enqueue:
        task = AgentTask(
            agent_slug=to_agent,
            skill=skill or DEFAULT_SKILL,
            trigger="message",
            payload={
                "message_id": str(message.id),
                "from_agent": from_agent,
                "body": body,
                "artifact_url": artifact_url,
            },
        )
        db.add(task)
        db.flush()
        message.task_id = task.id

    _mirror_to_slack(db, message)
    db.commit()
    db.refresh(message)
    return message


def create_investor_message(db: Session, body: str, artifact_url: str | None = None) -> AgentMessage:
    """Canal único: mensagem do investidor vai sempre pro CEO como diretriz."""
    return create_message(
        db,
        from_agent=INVESTOR,
        to_agent=CEO_SLUG,
        body=body,
        artifact_url=artifact_url,
        skill=INVESTOR_DIRECTIVE_SKILL,
    )


def list_messages(db: Session, limit: int = 50, before: datetime | None = None) -> list[AgentMessage]:
    q = db.query(AgentMessage)
    if before is not None:
        q = q.filter(AgentMessage.created_at < before)
    return q.order_by(AgentMessage.created_at.desc()).limit(min(limit, 200)).all()


# --- Tasks ---


def create_task(db: Session, data: dict) -> AgentTask:
    task = AgentTask(
        agent_slug=data["agent_slug"],
        skill=data["skill"],
        trigger=data.get("trigger", "manual"),
        payload=data.get("payload", {}),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(db: Session, status: str | None = None, limit: int = 100) -> list[AgentTask]:
    q = db.query(AgentTask)
    if status:
        q = q.filter(AgentTask.status == status)
    return q.order_by(AgentTask.created_at.desc()).limit(min(limit, 500)).all()


def claim_next_task(db: Session, runner_id: str) -> AgentTask | None:
    """Claim da task mais antiga cujo agente não está ocupado (1 running por agente)."""
    busy = select(AgentTask.agent_slug).where(AgentTask.status == "running")
    stmt = (
        select(AgentTask)
        .where(AgentTask.status == "queued", AgentTask.agent_slug.not_in(busy))
        .order_by(AgentTask.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = db.execute(stmt).scalars().first()
    if task is None:
        return None

    task.status = "running"
    task.claimed_by = runner_id
    task.claimed_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


def report_task(db: Session, task: AgentTask, data: dict) -> AgentTask:
    for field in ("status", "error", "result_summary"):
        if field in data and data[field] is not None:
            setattr(task, field, data[field])
    if data.get("cost_usd") is not None:
        task.cost_usd = Decimal(str(data["cost_usd"]))
    if data.get("status") in ("done", "failed"):
        task.finished_at = datetime.utcnow()
        if data["status"] == "failed":
            events.emit_event(
                db,
                source="empresa",
                event_type="run_failed",
                title=f"Task de @{task.agent_slug} falhou ({task.skill})",
                summary=(data.get("error") or "")[:400],
                ref_kind="agent_task",
                ref_id=task.id,
                url_path="/empresa",
            )
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: UUID) -> AgentTask | None:
    return db.query(AgentTask).filter(AgentTask.id == task_id).first()
