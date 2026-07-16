"""add planner_runs

Revision ID: 12a06171c704
Revises: b4c2d5e6f7a8
Create Date: 2026-07-16 00:04:06.732421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '12a06171c704'
down_revision: Union[str, None] = 'b4c2d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'planner_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('plan_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(), server_default='queued', nullable=False),
        sa.Column('narrative', sa.Text(), nullable=True),
        sa.Column('board_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('claude_cost_usd', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('claimed_by', sa.String(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'plan_date', name='uq_planner_runs_user_date'),
    )
    op.create_index('ix_planner_runs_status', 'planner_runs', ['status'], unique=False)
    op.create_index('ix_planner_runs_user', 'planner_runs', ['user_id'], unique=False)

    op.add_column('proposals', sa.Column('plan_run_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_proposals_plan_run_id', 'proposals', 'planner_runs',
        ['plan_run_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_proposals_plan_run_id', 'proposals', type_='foreignkey')
    op.drop_column('proposals', 'plan_run_id')
    op.drop_index('ix_planner_runs_user', table_name='planner_runs')
    op.drop_index('ix_planner_runs_status', table_name='planner_runs')
    op.drop_table('planner_runs')
