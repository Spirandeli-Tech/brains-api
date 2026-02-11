"""make_invoice_services_invoice_id_nullable

Revision ID: f7a8b9c0d1e2
Revises: a1b2c3d4e5f6
Create Date: 2026-02-10 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('invoice_services', 'invoice_id',
                    existing_type=sa.UUID(),
                    nullable=True)


def downgrade() -> None:
    # Delete orphan services (no invoice) before making column NOT NULL again
    op.execute("DELETE FROM invoice_services WHERE invoice_id IS NULL")
    op.alter_column('invoice_services', 'invoice_id',
                    existing_type=sa.UUID(),
                    nullable=False)
