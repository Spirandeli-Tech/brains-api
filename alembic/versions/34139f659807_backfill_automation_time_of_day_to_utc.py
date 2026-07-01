"""backfill_automation_time_of_day_to_utc

Revision ID: 34139f659807
Revises: f76feacb15c9
Create Date: 2026-07-01 00:00:00.000000

Going forward, Automation.time_of_day is stored as UTC clock time (the frontend
converts from the browser's local time on save). Existing rows were saved before that
conversion existed, so their stored value is effectively local wall-clock time as
entered. Shift them by the operator's UTC offset so existing schedules keep firing at
the same wall-clock local time the user originally configured.

The offset CANNOT be computed dynamically inside this migration: it runs inside the
`brains-api` container, which always runs in UTC regardless of the host/browser's real
timezone, so `datetime.now().astimezone()` in-container is meaningless here (it was
tried and confirmed to always yield an offset of 0). The offset must be supplied
explicitly at upgrade time via an alembic -x argument, e.g. for a host that is UTC-6:

    docker exec brains-api alembic upgrade 34139f659807 -x utc_offset_seconds=-21600

With no -x argument given, this is a no-op (safer than silently guessing wrong).

This is a one-shot, point-in-time backfill — it must land in the same deploy as the
frontend's UTC conversion and the claim query's time-gating logic (see automation
service `claim_next_automation_run`), otherwise automations will fire off by the host's
UTC offset during the gap.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = '34139f659807'
down_revision: Union[str, None] = 'f76feacb15c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _offset_seconds() -> int:
    x_args = context.get_x_argument(as_dictionary=True)
    return int(x_args.get("utc_offset_seconds", 0))


def upgrade() -> None:
    offset_seconds = _offset_seconds()
    if offset_seconds == 0:
        return
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE automations "
            "SET time_of_day = (time_of_day - (:offset_seconds || ' seconds')::interval)::time"
        ),
        {"offset_seconds": offset_seconds},
    )


def downgrade() -> None:
    offset_seconds = _offset_seconds()
    if offset_seconds == 0:
        return
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE automations "
            "SET time_of_day = (time_of_day + (:offset_seconds || ' seconds')::interval)::time"
        ),
        {"offset_seconds": offset_seconds},
    )
