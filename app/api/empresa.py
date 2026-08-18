"""Rotas do módulo Empresa — organograma vivo, feed de mensagens e fila de tasks.

User-facing: o investidor vê a empresa e fala com o CEO (canal único do
protocolo — POST /empresa/messages força o destinatário pro CEO e enfileira
ceo-diretriz). Runner-facing: claim/report de agent_tasks e criação de
mensagens pelos próprios agentes durante a execução das skills.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.empresa import (
    AgentRead,
    AgentSeedRequest,
    ClaimRequest,
    InvestorMessageCreate,
    MessageRead,
    RunnerMessageCreate,
    TaskCreate,
    TaskRead,
    TaskReport,
)
from app.services import empresa_service as svc

router = APIRouter(prefix="/empresa", tags=["empresa"])


def require_runner(x_runner_token: str | None = Header(default=None)) -> bool:
    if not settings.RUNNER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runner endpoints are disabled. Set RUNNER_TOKEN to enable.",
        )
    if x_runner_token != settings.RUNNER_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid runner token")
    return True


# --- User-facing endpoints ---


@router.get("/agents", response_model=list[AgentRead])
def list_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_agents(db)


@router.get("/feed", response_model=list[MessageRead])
def get_feed(
    limit: int = 50,
    before: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_messages(db, limit=limit, before=before)


@router.post("/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def send_investor_message(
    data: InvestorMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Canal único do protocolo: a mensagem do investidor vai sempre pro CEO."""
    try:
        return svc.create_investor_message(db, data.body, data.artifact_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    status_filter: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_tasks(db, status=status_filter, limit=limit)


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_task(db, data.model_dump())


# --- Runner-facing endpoints ---


@router.post("/runner/seed-agents")
def runner_seed_agents(
    data: AgentSeedRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    count = svc.seed_agents(db, [a.model_dump() for a in data.agents])
    return {"seeded": count}


@router.post("/runner/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def runner_create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    """Rituais: o runner enfileira tasks agendadas (fabrica/rituais.yaml)."""
    return svc.create_task(db, data.model_dump())


@router.post("/runner/claim", response_model=TaskRead | None)
def runner_claim(
    data: ClaimRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    return svc.claim_next_task(db, data.runner_id)


@router.patch("/runner/tasks/{task_id}", response_model=TaskRead)
def runner_report_task(
    task_id: UUID,
    data: TaskReport,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    task = svc.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return svc.report_task(db, task, data.model_dump(exclude_unset=True))


@router.post("/runner/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def runner_create_message(
    data: RunnerMessageCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    """Agentes conversam por aqui durante a execução das skills."""
    try:
        return svc.create_message(
            db,
            from_agent=data.from_agent,
            to_agent=data.to_agent,
            body=data.body,
            artifact_url=data.artifact_url,
            skill=data.skill,
            enqueue=data.enqueue,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
