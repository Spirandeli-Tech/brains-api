import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_value
from app.models.productivity_commit import ProductivityCommit
from app.models.productivity_connection import ProductivityConnection
from app.models.productivity_pull_request import ProductivityPullRequest
from app.services.bitbucket_provider import BitbucketProvider
from app.services.github_provider import GitHubAccessError, GitHubProvider

logger = logging.getLogger(__name__)

# Cap the first-time backfill so a NULL last_synced_at doesn't trigger a
# full-history crawl that hits GitHub rate limits and holds DB locks for
# 20+ minutes. Subsequent syncs use the connection's last_synced_at.
DEFAULT_BACKFILL_DAYS = 7

# Process-local guard against stampedes when the same connection is synced
# concurrently (e.g. user double-clicks Sync). Worker-local — fine for the
# single-uvicorn-worker setup; if we ever scale horizontally this needs to
# move to Postgres advisory locks.
_in_flight: set[UUID] = set()
_in_flight_lock = threading.Lock()


def is_sync_in_flight(connection_id: UUID) -> bool:
    with _in_flight_lock:
        return connection_id in _in_flight


def _claim_sync(connection_id: UUID) -> bool:
    with _in_flight_lock:
        if connection_id in _in_flight:
            return False
        _in_flight.add(connection_id)
        return True


def _release_sync(connection_id: UUID) -> None:
    with _in_flight_lock:
        _in_flight.discard(connection_id)


def _get_provider(connection: ProductivityConnection):
    pat = decrypt_value(connection.pat_encrypted)

    if connection.provider == "github":
        return GitHubProvider(
            pat=pat,
            username=connection.username,
            org=connection.workspace,
        )
    elif connection.provider == "bitbucket":
        return BitbucketProvider(
            pat=pat,
            username=connection.username,
            workspace=connection.workspace,
            external_account_id=connection.external_account_id,
        )
    else:
        raise ValueError(f"Unknown provider: {connection.provider}")


def sync_connection(connection_id: UUID, db: Session) -> dict:
    connection = db.query(ProductivityConnection).filter(
        ProductivityConnection.id == connection_id
    ).first()

    if not connection:
        raise ValueError("Connection not found")

    provider = _get_provider(connection)

    if connection.provider == "bitbucket" and not connection.external_account_id:
        try:
            info = asyncio.run(provider.get_current_user())
        except Exception as e:
            logger.warning(
                f"Bitbucket /user lookup failed for connection {connection_id}: {e}"
            )
            info = None
        if info and info.get("account_id"):
            connection.external_account_id = info["account_id"]
            provider.external_account_id = info["account_id"]
            db.commit()

    errors: list[str] = []
    total_commits = 0
    total_prs = 0
    rate_limited = False

    if connection.selected_repos:
        repos = connection.selected_repos
    else:
        try:
            repos = asyncio.run(provider.list_repositories())
        except Exception as e:
            logger.error(f"Failed to list repos for connection {connection_id}: {e}")
            return {
                "connection_id": connection_id,
                "status": "completed",
                "commits_synced": 0,
                "prs_synced": 0,
                "errors": [f"Failed to list repositories: {str(e)}"],
            }

    # Per-repo sync watermarks. A repo that has never been synced (no watermark
    # and no commits in the DB) gets a bounded backfill, so a repo added long
    # after the connection still picks up its recent history instead of being
    # silently bounded to the connection's last_synced_at.
    watermarks = dict(connection.repo_synced_at or {})
    existing_repos = {
        row[0]
        for row in db.query(ProductivityCommit.repository)
        .filter(ProductivityCommit.connection_id == connection_id)
        .distinct()
        .all()
    }
    conn_last_synced = connection.last_synced_at
    if conn_last_synced and conn_last_synced.tzinfo is None:
        conn_last_synced = conn_last_synced.replace(tzinfo=timezone.utc)

    def _since_for(repo: str) -> datetime:
        raw = watermarks.get(repo)
        if raw:
            dt = datetime.fromisoformat(raw)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        # Already-synced repo from before per-repo tracking existed: keep using
        # the connection watermark so we don't needlessly re-crawl it.
        if repo in existing_repos and conn_last_synced:
            return conn_last_synced
        # Brand-new repo: bounded backfill instead of a full-history crawl.
        logger.info(
            f"Connection {connection_id} repo {repo} has no watermark; "
            f"bounding backfill to {DEFAULT_BACKFILL_DAYS} days"
        )
        return datetime.now(timezone.utc) - timedelta(days=DEFAULT_BACKFILL_DAYS)

    for repo in repos:
        if rate_limited:
            errors.append(f"Skipped {repo}: GitHub rate limit reached")
            continue

        since = _since_for(repo)
        repo_errored = False

        try:
            commits_data = asyncio.run(provider.fetch_commits(repo, since))
            for c in commits_data:
                stmt = pg_insert(ProductivityCommit).values(
                    connection_id=connection_id,
                    hash=c["hash"],
                    short_hash=c["short_hash"],
                    message=c["message"],
                    author=c["author"],
                    date=c["date"],
                    additions=c["additions"],
                    deletions=c["deletions"],
                    repository=c["repository"],
                    is_merge=c.get("is_merge", False),
                ).on_conflict_do_nothing(
                    constraint="uq_commit_connection_hash_repo"
                )
                result = db.execute(stmt)
                if result.rowcount > 0:
                    total_commits += 1
            db.commit()
        except GitHubAccessError as e:
            db.rollback()
            repo_errored = True
            logger.warning(f"GitHub access error fetching commits for {repo}: {e}")
            errors.append(f"Commits error for {repo}: {e.message}")
            if e.status in (403, 429):
                rate_limited = True
                continue
        except Exception as e:
            db.rollback()
            repo_errored = True
            logger.warning(f"Failed to fetch commits for {repo}: {e}")
            errors.append(f"Commits error for {repo}: {str(e)}")

        try:
            prs_data = asyncio.run(provider.fetch_pull_requests(repo, since))
            for pr in prs_data:
                stmt = pg_insert(ProductivityPullRequest).values(
                    connection_id=connection_id,
                    number=pr["number"],
                    title=pr["title"],
                    status=pr["status"],
                    repository=pr["repository"],
                    url=pr["url"],
                    created_at_remote=pr["created_at_remote"],
                    merged_at=pr.get("merged_at"),
                ).on_conflict_do_update(
                    constraint="uq_pr_connection_number_repo",
                    set_={
                        "status": pr["status"],
                        "title": pr["title"],
                        "merged_at": pr.get("merged_at"),
                    },
                )
                result = db.execute(stmt)
                if result.rowcount > 0:
                    total_prs += 1
            db.commit()
        except GitHubAccessError as e:
            db.rollback()
            repo_errored = True
            logger.warning(f"GitHub access error fetching PRs for {repo}: {e}")
            errors.append(f"PRs error for {repo}: {e.message}")
            if e.status in (403, 429):
                rate_limited = True
                continue
        except Exception as e:
            db.rollback()
            repo_errored = True
            logger.warning(f"Failed to fetch PRs for {repo}: {e}")
            errors.append(f"PRs error for {repo}: {str(e)}")

        # Advance the per-repo watermark only when the repo synced cleanly, so a
        # partial/errored repo is retried (inserts are idempotent) next run.
        if not repo_errored:
            watermarks[repo] = datetime.now(timezone.utc).isoformat()
            connection.repo_synced_at = dict(watermarks)
            db.commit()

    # Drop watermarks for repos no longer tracked so the map can't grow unbounded.
    pruned = {r: ts for r, ts in watermarks.items() if r in set(repos)}
    if pruned != (connection.repo_synced_at or {}):
        connection.repo_synced_at = pruned
        db.commit()

    if not errors:
        connection.last_synced_at = datetime.utcnow()
        db.commit()

    return {
        "connection_id": connection_id,
        "status": "completed",
        "commits_synced": total_commits,
        "prs_synced": total_prs,
        "errors": errors,
    }
