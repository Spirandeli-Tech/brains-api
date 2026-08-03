from datetime import datetime

from pydantic import BaseModel


class HeartbeatIn(BaseModel):
    runner_id: str
    poll_interval: str | None = None
    dry_run: bool | None = None
    version: str | None = None


class HeartbeatOut(BaseModel):
    """Commands riding back on the heartbeat — the only channel that reaches the
    runner while its main loop is blocked inside a job."""

    restart_requested: bool = False


class RunnerStatus(BaseModel):
    runner_id: str
    last_seen_at: datetime
    online: bool
    seconds_since_last_seen: float
    poll_interval: str | None = None
    dry_run: bool | None = None
    version: str | None = None
    # A restart was asked for and the runner hasn't picked it up yet.
    restart_pending: bool = False


class RestartOut(BaseModel):
    runner_id: str
    requested_at: datetime
    # In-flight runs failed by the request (the restart kills them).
    failed_runs: int


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
    # Front-end route where this run's log/detail lives (null when the kind has
    # no detail screen yet), and whether it can still be dropped from the queue.
    url_path: str | None = None
    can_cancel: bool = False


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
    url_path: str | None = None


class RunnerOverview(BaseModel):
    now: datetime
    runners: list[RunnerStatus]
    current: list[QueueItem]
    queued: list[QueueItem]
    recent: list[RecentRun] = []
