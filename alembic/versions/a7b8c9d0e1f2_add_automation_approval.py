"""add_automation_approval

Dá ao caminho de AUTOMAÇÃO um gate de aprovação humana, espelhando o que
implementation/code-review/address-PR já têm. Duas colunas:

- `automations.requires_approval`: quando true, o runner pausa a automação após a
  "fase 1" em vez de concluir, e ela aparece na board "Aguardando você".
- `automation_runs.phase`: 1 = fase de preparação (roda, gera o preview e pausa em
  `awaiting_approval`); 2 = fase de conclusão (disparada quando o usuário aprova,
  o mesmo run é re-enfileirado com phase=2 e o runner o leva até o fim).

Nenhuma coluna de preview nova: o preview do card reusa `automation_runs.result_summary`,
que o runner já preenche com o texto final da execução.

Revision ID: a7b8c9d0e1f2
Revises: f4a5b6c7d8e9
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'automations',
        sa.Column(
            'requires_approval',
            sa.Boolean(),
            server_default='false',
            nullable=False,
        ),
    )
    op.add_column(
        'automation_runs',
        sa.Column(
            'phase',
            sa.Integer(),
            server_default='1',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('automation_runs', 'phase')
    op.drop_column('automations', 'requires_approval')
