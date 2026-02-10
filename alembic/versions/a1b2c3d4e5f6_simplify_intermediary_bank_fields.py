"""simplify_intermediary_bank_fields

Revision ID: a1b2c3d4e5f6
Revises: c3a7f1b2d4e6
Create Date: 2026-02-10 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c3a7f1b2d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new consolidated column
    op.add_column("bank_accounts", sa.Column("intermediary_bank_info", sa.String(), nullable=True))

    # Backfill: concatenate existing intermediary fields into the new text field
    op.execute(
        """
        UPDATE bank_accounts
        SET intermediary_bank_info = CONCAT_WS(
            E'\\n',
            CASE WHEN intermediary_bank_name IS NOT NULL THEN 'Bank: ' || intermediary_bank_name END,
            CASE WHEN intermediary_swift_code IS NOT NULL THEN 'SWIFT: ' || intermediary_swift_code END,
            CASE WHEN intermediary_account_number IS NOT NULL THEN 'Account: ' || intermediary_account_number END,
            CASE WHEN intermediary_bank_address IS NOT NULL THEN 'Address: ' || intermediary_bank_address END
        )
        WHERE intermediary_swift_code IS NOT NULL
           OR intermediary_bank_name IS NOT NULL
           OR intermediary_bank_address IS NOT NULL
           OR intermediary_account_number IS NOT NULL
        """
    )

    # Drop old columns
    op.drop_column("bank_accounts", "intermediary_swift_code")
    op.drop_column("bank_accounts", "intermediary_bank_name")
    op.drop_column("bank_accounts", "intermediary_bank_address")
    op.drop_column("bank_accounts", "intermediary_account_number")


def downgrade() -> None:
    op.add_column("bank_accounts", sa.Column("intermediary_account_number", sa.String(), nullable=True))
    op.add_column("bank_accounts", sa.Column("intermediary_bank_address", sa.String(), nullable=True))
    op.add_column("bank_accounts", sa.Column("intermediary_bank_name", sa.String(), nullable=True))
    op.add_column("bank_accounts", sa.Column("intermediary_swift_code", sa.String(), nullable=True))
    op.drop_column("bank_accounts", "intermediary_bank_info")
