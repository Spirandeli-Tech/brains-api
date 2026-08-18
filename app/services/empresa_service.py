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


# --- Interruptor da empresa (o botão do investidor) ---

PAUSE_KEY = "empresa_pausada"


def empresa_pausada(db: Session) -> bool:
    from app.models.base import SystemMeta

    row = db.query(SystemMeta).filter(SystemMeta.key == PAUSE_KEY).first()
    return bool(row and row.value == "true")


def set_empresa_pausada(db: Session, pausada: bool) -> bool:
    from app.models.base import SystemMeta

    row = db.query(SystemMeta).filter(SystemMeta.key == PAUSE_KEY).first()
    if row is None:
        row = SystemMeta(key=PAUSE_KEY, value="false")
        db.add(row)
    row.value = "true" if pausada else "false"
    db.commit()
    # broadcast no feed/Slack — a empresa inteira (e o investidor no celular) fica sabendo
    create_message(
        db,
        from_agent="investidor",
        to_agent=None,
        body=("🔴 A empresa foi DESLIGADA pelo investidor. Nada novo inicia; execuções em "
              "andamento concluem e param." if pausada
              else "🟢 A empresa foi RELIGADA pelo investidor. Operação normal retomada."),
        enqueue=False,
    )
    return pausada


def diagnostico(db: Session) -> dict:
    """'Por que está tudo parado?' — a corrente inteira explicada em linguagem humana.

    Cada check é {nome, ok, detalhe}. `motivos` sintetiza por que nada está se
    movendo AGORA (fila vazia ≠ problema: anti-busywork é regra da casa).
    """
    from datetime import timedelta

    from app.models import ImplementationRun, RunnerHeartbeat

    now = datetime.utcnow()
    checks: list[dict] = []
    motivos: list[str] = []

    if empresa_pausada(db):
        checks.append({"nome": "Interruptor", "ok": False,
                       "detalhe": "EMPRESA DESLIGADA pelo investidor"})
        motivos.insert(0, "A empresa está DESLIGADA pelo investidor — nada novo inicia até religar (botão na página).")

    hb = db.query(RunnerHeartbeat).order_by(RunnerHeartbeat.last_seen_at.desc()).first()
    if hb and now - hb.last_seen_at < timedelta(minutes=2):
        age = int((now - hb.last_seen_at).total_seconds())
        checks.append({"nome": "Runner", "ok": True,
                       "detalhe": f"vivo ({hb.runner_id}, visto há {age}s)" + (" · DRY-RUN ligado" if hb.dry_run else "")})
        if hb.dry_run:
            motivos.append("O runner está em dry-run: execuções são narradas, sem efeito real (rede de segurança da estreia).")
    else:
        checks.append({"nome": "Runner", "ok": False,
                       "detalhe": "sem heartbeat há mais de 2 min — o processo do runner provavelmente não está rodando na máquina"})
        motivos.append("O runner está fora do ar — nada é executado sem ele. Iniciar: cd runner && .venv/bin/python runner.py (com CLAUDE_CODE_OAUTH_TOKEN no ambiente).")

    queued = db.query(AgentTask).filter(AgentTask.status == "queued").count()
    running = db.query(AgentTask).filter(AgentTask.status == "running").count()
    checks.append({"nome": "Fila da empresa", "ok": True,
                   "detalhe": f"{running} em execução · {queued} aguardando"})
    if queued == 0 and running == 0:
        motivos.append("Nenhuma task na fila dos agentes — ninguém foi acionado (mensagem, ritual ou evento). Fila vazia é estado legítimo (anti-busywork).")

    rituais = list_rituais()
    if rituais:
        nunca = [r["name"] for r in rituais if not r["last_fired"]]
        det = f"{len(rituais)} agendados"
        if nunca:
            det += f" · ainda não dispararam: {', '.join(nunca)}"
        checks.append({"nome": "Rituais", "ok": True, "detalhe": det})
        if len(nunca) == len(rituais):
            motivos.append("Nenhum ritual disparou ainda — o primeiro é o ceo-ritual-semanal, segunda-feira às 08:00.")
    else:
        checks.append({"nome": "Rituais", "ok": False, "detalhe": "rituais.yaml não montado/ilegível"})

    impl_q = db.query(ImplementationRun).filter(ImplementationRun.status == "queued").count()
    impl_r = db.query(ImplementationRun).filter(ImplementationRun.status == "running").count()
    impl_a = db.query(ImplementationRun).filter(ImplementationRun.status == "awaiting_approval").count()
    checks.append({"nome": "Pipeline de implementação", "ok": True,
                   "detalhe": f"{impl_r} rodando · {impl_q} na fila · {impl_a} aguardando aprovação"})
    if impl_a:
        motivos.append(f"{impl_a} run(s) de implementação PAUSADA(s) esperando aprovação do investidor — board 'Aguardando você'.")
    if impl_q == 0 and impl_r == 0 and impl_a == 0:
        motivos.append("Nenhuma run de implementação ativa — tickets Ready só viram trabalho quando uma run é lançada (a ponte automática é o ST-159).")

    return {"checks": checks, "motivos": motivos}


import re as _re


def get_skill_doc(skill: str) -> str | None:
    """Conteúdo do SKILL.md de uma skill da fábrica (pro diálogo 'o que este ritual faz')."""
    if not _re.fullmatch(r"[a-z0-9-]+", skill):
        return None
    path = os.path.join(FABRICA_DIR, ".claude", "skills", skill, "SKILL.md")
    if not os.path.exists(path):
        return None
    try:
        return open(path).read()
    except OSError:
        return None


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

    def _task_detail(t: AgentTask) -> str:
        """Descrição humana do que o agente está fazendo agora (pro organograma)."""
        p = t.payload or {}
        if p.get("ritual"):
            return f"ritual {p['ritual']}"
        if p.get("body"):
            body = str(p["body"])
            de = f" (de @{p['from_agent']})" if p.get("from_agent") else ""
            return (body[:110] + "…" if len(body) > 110 else body) + de
        return t.skill

    running = {
        t.agent_slug: t
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

    # Overlay do pipeline de implementação: o step em execução de uma run ativa
    # mapeia pro agente do ofício (Noé implementa, Natã revisa, Tomé testa) —
    # sem isso o organograma diz "disponível" com o agente suando no pipeline.
    from app.models import ImplementationRun, ImplementationStep

    STEP_AGENT = {"enrich_ticket": "noe", "move_to_progress": "noe", "implement": "noe",
                  "open_pr": "noe", "address_feedback": "noe",
                  "code_review": "nata", "qa_notes": "tome"}
    STEP_LABEL = {"implement": "implementando", "open_pr": "abrindo PR",
                  "code_review": "revisando código", "qa_notes": "rodando QA",
                  "enrich_ticket": "enriquecendo spec", "move_to_progress": "movendo ticket",
                  "address_feedback": "ajustando feedback"}
    pipeline_overlay: dict[str, str] = {}
    active_runs = db.query(ImplementationRun).filter(ImplementationRun.status == "running").all()
    for r in active_runs:
        step = (db.query(ImplementationStep)
                .filter(ImplementationStep.run_id == r.id, ImplementationStep.status == "running")
                .first())
        if step and step.kind in STEP_AGENT:
            slug = STEP_AGENT[step.kind]
            pipeline_overlay[slug] = f"{r.ticket_key or 'ticket'} · {STEP_LABEL.get(step.kind, step.kind)} (pipeline)"

    result = []
    for a in agents:
        running_task = running.get(a.slug)
        current_skill = running_task.skill if running_task else None
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
                "status": ("running" if (current_skill or a.slug in pipeline_overlay)
                           else ("queued" if queued_counts.get(a.slug) else "idle")),
                "current_skill": current_skill or (("pipeline") if a.slug in pipeline_overlay else None),
                "current_task_detail": (_task_detail(running_task) if running_task
                                        else pipeline_overlay.get(a.slug)),
                "queued_count": int(queued_counts.get(a.slug, 0)),
                "total_cost_usd": float(costs.get(a.slug) or 0),
            }
        )
    return result


# --- Messages + dispatcher ---


# persona de cada agente no Slack (nome de exibição + emoji), até o Bezalel
# desenhar os retratos oficiais (viram custom emojis do workspace)
SLACK_PERSONAS = {
    "salomao": ("Salomão · CEO", ":crown:"),
    "esdras": ("Esdras · Product Manager", ":scroll:"),
    "neemias": ("Neemias · CTO", ":building_construction:"),
    "mateus": ("Mateus · CFO", ":moneybag:"),
    "paulo": ("Paulo · CMO", ":mega:"),
    "noe": ("Noé · Dev", ":hammer_and_wrench:"),
    "nata": ("Natã · Code Review", ":balance_scale:"),
    "tome": ("Tomé · QA", ":test_tube:"),
    "bezalel": ("Bezalel · Designer", ":art:"),
    "calebe": ("Calebe · Pesquisa", ":telescope:"),
    "investidor": ("Lucas · Investidor", ":large_yellow_circle:"),
}


def _mirror_to_slack(db: Session, message: AgentMessage) -> None:
    """Espelha a mensagem no canal da empresa como persona do agente (nunca levanta)."""
    from app.services import notifier

    name, emoji = SLACK_PERSONAS.get(message.from_agent, (f"@{message.from_agent}", ":robot_face:"))
    text = message.body
    if message.to_agent:
        to_name = SLACK_PERSONAS.get(message.to_agent, (f"@{message.to_agent}",))[0].split(" · ")[0]
        text = f"*@{to_name}* — {text}"
    if message.artifact_url:
        text += f"\n<{message.artifact_url}|artefato>"
    notifier.post_agent_message(name, emoji, text)
    # registro do evento na plataforma (UI/histórico); o notifier ignora este
    # event_type — o post persona acima é o espelho
    events.emit_event(
        db,
        source="empresa",
        event_type="agent_message",
        title=f"@{message.from_agent}" + (f" → @{message.to_agent}" if message.to_agent else ""),
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
    """Claim da task mais antiga cujo agente não está ocupado (1 running por agente).

    Auto-recuperação de órfãs: task 'running' há mais de 45 min (runner morreu no
    meio — restart, crash) volta pra fila antes do claim; sem isso, a task-zumbi
    segura o cadeado de identidade do agente pra sempre.
    """
    from datetime import timedelta

    if empresa_pausada(db):
        return None  # interruptor do investidor: nada novo é assumido

    stale_cutoff = datetime.utcnow() - timedelta(minutes=45)
    stale = (
        db.query(AgentTask)
        .filter(AgentTask.status == "running", AgentTask.claimed_at < stale_cutoff)
        .all()
    )
    for t in stale:
        t.status = "queued"
        t.claimed_by = None
        t.claimed_at = None
        t.updated_at = datetime.utcnow()
    if stale:
        db.commit()

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
