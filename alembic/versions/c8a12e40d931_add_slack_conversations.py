"""Durable Slack conversations and delivery outbox."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c8a12e40d931"
down_revision = "2f2371908e65"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        *[sa.Column(n, sa.String(), nullable=False) for n in ("workspace_id", "app_id", "channel_id", "thread_ts")],
        *[sa.Column(n, sa.String()) for n in ("session_id", "session_host", "session_cwd")],
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "app_id", "channel_id", "thread_ts"))
    op.create_table("conversation_turns",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False, unique=True),
        sa.Column("message_ts", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        *[sa.Column(n, sa.Text()) for n in ("response", "progress", "error")],
        *[sa.Column(n, sa.String()) for n in ("cost_usd", "runner_id", "claim_token")],
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
        sa.UniqueConstraint("conversation_id", "sequence"),
        sa.UniqueConstraint("conversation_id", "message_ts"))
    op.create_index("ix_conversation_turns_conversation_id", "conversation_turns", ["conversation_id"])
    op.create_index("ix_conversation_turns_status", "conversation_turns", ["status"])
    op.create_table("conversation_deliveries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False, unique=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("slack_ts", sa.String()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_conversation_deliveries_status", "conversation_deliveries", ["status"])
    # Apply the existing database guard to newly created tables, too.
    from app.core.org_blocklist import install_db_guard
    from contextlib import contextmanager
    class MigrationConnection:
        @contextmanager
        def begin(self):
            yield op.get_bind()
    install_db_guard(MigrationConnection())


def downgrade():
    for table in ("conversation_deliveries", "conversation_turns", "conversations"):
        op.drop_table(table)
