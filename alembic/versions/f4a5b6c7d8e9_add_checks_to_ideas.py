"""add_checks_to_ideas

Substitui `ideas.theme_filter` (prosa solta) por `ideas.checks`, onde cada check
carrega um **veredito explícito** além da nota.

Motivo: o score de uma ideia não pode ser inferido de texto livre. `theme_filter`
guardava strings como "Sim — pesquisa encontrou...", e derivar pass/fail de
prefixo de string é rigor falso: a primeira nota que começasse com "Não achei
evidência, mas..." pontuaria como aprovada. Veredito é dado, não interpretação.

Backfill: as notas de `theme_filter` viram `checks.<key>.note` preservadas na
íntegra, e o estado entra como `unknown` — inclusive nas ideias que eu mesmo
avaliei em prosa. Marcar `unknown` é mais honesto que adivinhar: o estado passa a
ser uma afirmação de quem revisou, não uma leitura minha do texto.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ideas',
        sa.Column(
            'checks',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=False,
        ),
    )

    # theme_filter {demand, angle, immediate_value} -> checks {<key>: {state, note}}.
    # `scene` nasce sem nota (nunca existiu como campo) e `facts` é derivado de
    # `trustworthy` em tempo de leitura, então nenhum dos dois entra aqui.
    op.execute(
        """
        UPDATE ideas SET checks = (
          SELECT jsonb_object_agg(dst, jsonb_build_object('state', 'unknown', 'note', val))
          FROM (
            SELECT 'demand' AS dst, theme_filter->>'demand' AS val
            UNION ALL SELECT 'angle', theme_filter->>'angle'
            UNION ALL SELECT 'value', theme_filter->>'immediate_value'
          ) m
          WHERE val IS NOT NULL AND val <> ''
        )
        WHERE theme_filter IS NOT NULL AND theme_filter <> '{}'::jsonb
        """
    )
    op.execute("UPDATE ideas SET checks = '{}'::jsonb WHERE checks IS NULL")

    op.drop_column('ideas', 'theme_filter')


def downgrade() -> None:
    op.add_column(
        'ideas',
        sa.Column(
            'theme_filter',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE ideas SET theme_filter = jsonb_strip_nulls(jsonb_build_object(
          'demand', checks->'demand'->>'note',
          'angle', checks->'angle'->>'note',
          'immediate_value', checks->'value'->>'note'
        ))
        """
    )
    op.drop_column('ideas', 'checks')
