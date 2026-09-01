"""merge empresa agent branch into main line

Revision ID: 2f2371908e65
Revises: 31f4c9ab7de1, f3d4e5a6b7c8
Create Date: 2026-09-01

O histórico bifurcou em b8c9d0e1f2a3: um ramo seguiu com as migrations do dia a
dia (automations, runner_heartbeats) e o outro criou as tabelas do módulo Empresa
(agents, agent_tasks, agent_messages). Só o primeiro ramo foi aplicado, então o
banco ficou sem agent_tasks e `POST /empresa/runner/claim` respondia 500 a cada
poll do runner (UndefinedTable).

Merge vazio — não há DDL a conciliar: os dois ramos tocam tabelas disjuntas.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "2f2371908e65"
down_revision: Union[str, Sequence[str], None] = ("31f4c9ab7de1", "f3d4e5a6b7c8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
