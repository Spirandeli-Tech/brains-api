from datetime import datetime

from pydantic import BaseModel


class HeartbeatIn(BaseModel):
    runner_id: str
    poll_interval: str | None = None
    dry_run: bool | None = None
    version: str | None = None


class RunnerStatus(BaseModel):
    runner_id: str
    last_seen_at: datetime
    online: bool
    seconds_since_last_seen: float
    poll_interval: str | None = None
    dry_run: bool | None = None
    version: str | None = None


class QueueItem(BaseModel):
    kind: str  # automation | implementation | code_review | address_pr | planner
    id: str
    title: str
    subtitle: str | None = None
    connection_name: str | None = None
    # running | queued | waiting | awaiting_approval
    display_status: str
    is_manual: bool | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    due_at: datetime | None = None
    error: str | None = None


class RecentRun(BaseModel):
    kind: str  # automation | implementation | code_review | address_pr | planner
    id: str
    title: str
    subtitle: str | None = None
    connection_name: str | None = None
    status: str  # done | failed | cancelled
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error: str | None = None


class RunnerOverview(BaseModel):
    now: datetime
    runners: list[RunnerStatus]
    current: list[QueueItem]
    queued: list[QueueItem]
    recent: list[RecentRun] = []
