import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.encryption import decrypt_value, encrypt_value, mask_pat
from app.models.contract import Contract
from app.models.local_commit import LocalCommit
from app.models.productivity_commit import ProductivityCommit
from app.models.productivity_connection import ProductivityConnection
from app.models.productivity_pull_request import ProductivityPullRequest
from app.models.user import User
from app.models.user_git_email import UserGitEmail
from app.schemas.productivity import (
    AggregatedStats,
    CommitRead,
    ConnectionCreate,
    ConnectionListItem,
    ConnectionRead,
    ConnectionStats,
    ConnectionUpdate,
    GitEmailCreate,
    GitEmailRead,
    PullRequestRead,
    SyncResult,
    UserActivityResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from app.services.bitbucket_provider import BitbucketProvider
from app.services.github_provider import GitHubAccessError, GitHubProvider
from app.services.productivity_sync import sync_connection

router = APIRouter(prefix="/productivity", tags=["productivity"])


def _end_of_day(date_str: str) -> datetime:
    """Convert a date string like '2026-04-07' to '2026-04-08 00:00:00' for inclusive filtering."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt + timedelta(days=1)


def _sync_in_background(connection_id: UUID) -> None:
    from app.core.db import SessionLocal
    db = SessionLocal()
    try:
        conn = db.query(ProductivityConnection).filter(
            ProductivityConnection.id == connection_id
        ).first()
        if conn:
            sync_connection(connection_id, db)
    except Exception:
        db.rollback()
    finally:
        db.close()


def _to_connection_read(conn: ProductivityConnection) -> dict:
    pat = decrypt_value(conn.pat_encrypted)
    data = {
        "id": conn.id,
        "provider": conn.provider,
        "username": conn.username,
        "workspace": conn.workspace,
        "contract_id": conn.contract_id,
        "custom_name": conn.custom_name,
        "display_name": conn.display_name,
        "pat_masked": mask_pat(pat),
        "selected_repos": conn.selected_repos,
        "is_primary": conn.is_primary,
        "last_synced_at": conn.last_synced_at,
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }
    return data


def _clear_other_primaries(
    db: Session, user_id: UUID, provider: str, exclude_id: UUID | None = None
) -> None:
    query = db.query(ProductivityConnection).filter(
        ProductivityConnection.created_by_user_id == user_id,
        ProductivityConnection.provider == provider,
        ProductivityConnection.is_primary.is_(True),
    )
    if exclude_id is not None:
        query = query.filter(ProductivityConnection.id != exclude_id)
    for other in query.all():
        other.is_primary = False


def _validate_token(provider: str, pat: str, username: str, workspace: str | None) -> bool:
    if provider == "github":
        client = GitHubProvider(pat=pat, username=username, org=workspace)
    elif provider == "bitbucket":
        client = BitbucketProvider(pat=pat, username=username, workspace=workspace)
    else:
        return False
    return asyncio.run(client.validate_token())


def _resolve_bitbucket_account(pat: str, username: str) -> str:
    """Verify the PAT belongs to the claimed Bitbucket username and return
    its account_id. Raises HTTPException(400) on any mismatch — this is the
    setup-time guard for fix #3."""
    provider = BitbucketProvider(pat=pat, username=username)
    info = asyncio.run(provider.get_current_user())
    if not info or not info.get("account_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Could not load the Bitbucket account for this token. "
                "Make sure the app password has the `account:read` scope."
            ),
        )
    claimed = (username or "").strip().lower()
    nickname = (info.get("nickname") or "").lower()
    legacy_username = (info.get("username") or "").lower()
    if claimed and claimed not in {nickname, legacy_username}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The PAT belongs to '{info.get('nickname') or info.get('display_name')}', "
                f"not '{username}'. Reconnect with the correct username."
            ),
        )
    return info["account_id"]


# --- Token Validation ---


@router.post("/validate-token", response_model=ValidateTokenResponse)
def validate_token_endpoint(
    data: ValidateTokenRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        if data.provider == "github":
            provider = GitHubProvider(pat=data.pat, username=data.username)
            valid = asyncio.run(provider.validate_token())
            orgs = asyncio.run(provider.list_organizations()) if valid else []
        elif data.provider == "bitbucket":
            provider = BitbucketProvider(pat=data.pat, username=data.username)
            valid = asyncio.run(provider.validate_token())
            orgs = asyncio.run(provider.list_workspaces()) if valid else []
        else:
            valid = False
            orgs = []
    except Exception:
        valid = False
        orgs = []

    return ValidateTokenResponse(valid=valid, organizations=orgs)


@router.post("/list-repos", response_model=list[str])
def list_repos_endpoint(
    data: ValidateTokenRequest,
    workspace: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    if data.provider == "github":
        provider = GitHubProvider(pat=data.pat, username=data.username, org=workspace)
    elif data.provider == "bitbucket":
        provider = BitbucketProvider(pat=data.pat, username=data.username, workspace=workspace)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {data.provider}")

    try:
        return asyncio.run(provider.list_repositories())
    except GitHubAccessError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list repositories: {e}")


# --- Local commit ingestion (from shell hook) ---


@router.post("/local-commits/flush")
async def flush_local_commits(request: Request, db: Session = Depends(get_db)):
    body = (await request.body()).decode("utf-8", errors="replace")
    received = 0
    stored = 0
    duplicates = 0
    errors: list[str] = []

    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        received += 1
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {received}: invalid JSON ({e})")
            continue

        try:
            h = data["hash"]
            remote = data.get("remote") or ""
            existing = (
                db.query(LocalCommit)
                .filter(LocalCommit.hash == h, LocalCommit.remote_url == remote)
                .first()
            )
            if existing:
                duplicates += 1
                continue

            try:
                committed_at = datetime.fromisoformat(data["timestamp"])
            except (ValueError, KeyError):
                committed_at = datetime.now(timezone.utc)

            commit = LocalCommit(
                hash=h,
                short_hash=h[:7],
                message=data.get("message") or "",
                author=data.get("author") or "",
                email=data.get("email") or "",
                committed_at=committed_at,
                branch=data.get("branch") or "",
                additions=int(data.get("additions") or 0),
                deletions=int(data.get("deletions") or 0),
                repo_name=data.get("repo") or "",
                remote_url=remote,
                source=data.get("source") or "qwe",
            )
            db.add(commit)
            db.commit()
            stored += 1
        except IntegrityError:
            db.rollback()
            duplicates += 1
        except Exception as e:
            db.rollback()
            errors.append(f"line {received}: {e}")

    return {"received": received, "stored": stored, "duplicates": duplicates, "errors": errors}


_SSH_REMOTE = re.compile(r"^[^@]+@[^:]+:([^/]+)/(.+)$")
_PROTO_REMOTE = re.compile(r"^[a-z]+://[^/]+/(.+)$")


def _normalize_remote(remote: str, fallback_repo_name: str) -> str:
    if not remote:
        return f"(local) {fallback_repo_name}" if fallback_repo_name else "(local)"
    s = remote.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    m = _SSH_REMOTE.match(s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = _PROTO_REMOTE.match(s)
    if m:
        parts = m.group(1).split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
        return m.group(1)
    return s


@router.get("/local-commits/by-repo")
def local_commits_by_repo(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        to_dt = _end_of_day(to_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    aliases = {
        e
        for (e,) in db.query(UserGitEmail.email).filter(
            UserGitEmail.user_id == current_user.id
        )
    }
    aliases.add(current_user.email.lower())
    emails = [e.lower() for e in aliases]

    rows = (
        db.query(
            LocalCommit.remote_url,
            LocalCommit.repo_name,
            func.count(LocalCommit.id).label("commits"),
            func.sum(LocalCommit.additions).label("additions"),
            func.sum(LocalCommit.deletions).label("deletions"),
            func.max(LocalCommit.committed_at).label("last_commit"),
        )
        .filter(
            func.lower(LocalCommit.email).in_(emails),
            LocalCommit.committed_at >= from_dt,
            LocalCommit.committed_at < to_dt,
        )
        .group_by(LocalCommit.remote_url, LocalCommit.repo_name)
        .all()
    )

    # Merge entries that normalize to the same display name (SSH vs HTTPS variants).
    merged: dict[str, dict] = {}
    for r in rows:
        display = _normalize_remote(r.remote_url, r.repo_name)
        bucket = merged.setdefault(
            display,
            {
                "display": display,
                "remote_url": r.remote_url,
                "repo_name": r.repo_name,
                "commits": 0,
                "additions": 0,
                "deletions": 0,
                "last_commit": None,
            },
        )
        bucket["commits"] += r.commits
        bucket["additions"] += int(r.additions or 0)
        bucket["deletions"] += int(r.deletions or 0)
        if r.last_commit and (bucket["last_commit"] is None or r.last_commit > bucket["last_commit"]):
            bucket["last_commit"] = r.last_commit

    result = sorted(merged.values(), key=lambda x: x["commits"], reverse=True)
    return result


# --- Git email aliases (which git emails belong to the current user) ---


@router.get("/git-emails", response_model=list[GitEmailRead])
def list_git_emails(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(UserGitEmail)
        .filter(UserGitEmail.user_id == current_user.id)
        .order_by(UserGitEmail.created_at.asc())
        .all()
    )


@router.post("/git-emails", response_model=GitEmailRead, status_code=status.HTTP_201_CREATED)
def add_git_email(
    payload: GitEmailCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(UserGitEmail)
        .filter(UserGitEmail.user_id == current_user.id, UserGitEmail.email == payload.email)
        .first()
    )
    if existing:
        return existing

    entry = UserGitEmail(user_id=current_user.id, email=payload.email)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return (
            db.query(UserGitEmail)
            .filter(UserGitEmail.user_id == current_user.id, UserGitEmail.email == payload.email)
            .first()
        )
    db.refresh(entry)
    return entry


@router.delete("/git-emails/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_git_email(
    email_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(UserGitEmail)
        .filter(UserGitEmail.id == email_id, UserGitEmail.user_id == current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Git email not found")
    db.delete(entry)
    db.commit()
    return None


# --- Connections CRUD ---


@router.get("/connections", response_model=list[ConnectionListItem])
def list_connections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ProductivityConnection)
        .filter(ProductivityConnection.created_by_user_id == current_user.id)
        .order_by(ProductivityConnection.created_at.desc())
        .all()
    )


@router.get("/connections/{connection_id}", response_model=ConnectionRead)
def get_connection(
    connection_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return _to_connection_read(conn)


@router.get("/connections/{connection_id}/repos", response_model=list[str])
def list_connection_repos(
    connection_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    pat = decrypt_value(conn.pat_encrypted)
    try:
        if conn.provider == "github":
            provider = GitHubProvider(pat=pat, username=conn.username, org=conn.workspace)
        elif conn.provider == "bitbucket":
            provider = BitbucketProvider(pat=pat, username=conn.username, workspace=conn.workspace)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {conn.provider}")
        return asyncio.run(provider.list_repositories())
    except GitHubAccessError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list repositories: {e}")


@router.post("/connections", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    data: ConnectionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    display_name = data.custom_name or ""
    if data.contract_id:
        contract = (
            db.query(Contract)
            .filter(
                Contract.id == data.contract_id,
                Contract.created_by_user_id == current_user.id,
            )
            .first()
        )
        if not contract:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
        display_name = contract.name

    existing_primary_count = (
        db.query(func.count(ProductivityConnection.id))
        .filter(
            ProductivityConnection.created_by_user_id == current_user.id,
            ProductivityConnection.provider == data.provider,
            ProductivityConnection.is_primary.is_(True),
        )
        .scalar()
    )
    is_primary = data.is_primary or existing_primary_count == 0

    if is_primary:
        _clear_other_primaries(db, current_user.id, data.provider)

    external_account_id: str | None = None
    if data.provider == "bitbucket":
        external_account_id = _resolve_bitbucket_account(data.pat, data.username)

    conn = ProductivityConnection(
        created_by_user_id=current_user.id,
        provider=data.provider,
        pat_encrypted=encrypt_value(data.pat),
        username=data.username,
        workspace=data.workspace,
        external_account_id=external_account_id,
        contract_id=data.contract_id,
        custom_name=data.custom_name,
        display_name=display_name,
        selected_repos=data.selected_repos or [],
        is_primary=is_primary,
    )
    db.add(conn)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A connection with this provider, username, and organization already exists.",
        )
    db.refresh(conn)

    background_tasks.add_task(_sync_in_background, conn.id)

    return _to_connection_read(conn)


@router.put("/connections/{connection_id}", response_model=ConnectionRead)
def update_connection(
    connection_id: UUID,
    data: ConnectionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    update_data = data.model_dump(exclude_unset=True)

    effective_username = data.username or conn.username
    pat_changed = False
    username_changed = (
        "username" in update_data and update_data["username"] != conn.username
    )

    if "pat" in update_data:
        pat = update_data.pop("pat")
        if pat:
            if not _validate_token(conn.provider, pat, effective_username, data.workspace or conn.workspace):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid personal access token.",
                )
            conn.pat_encrypted = encrypt_value(pat)
            pat_changed = True

    if conn.provider == "bitbucket" and (pat_changed or username_changed):
        pat_plain = decrypt_value(conn.pat_encrypted)
        conn.external_account_id = _resolve_bitbucket_account(
            pat_plain, effective_username
        )

    if "contract_id" in update_data:
        contract_id = update_data.get("contract_id")
        if contract_id:
            contract = (
                db.query(Contract)
                .filter(
                    Contract.id == contract_id,
                    Contract.created_by_user_id == current_user.id,
                )
                .first()
            )
            if not contract:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
            conn.display_name = contract.name
        elif update_data.get("custom_name"):
            conn.display_name = update_data["custom_name"]

    if update_data.get("is_primary") is True:
        _clear_other_primaries(db, current_user.id, conn.provider, exclude_id=conn.id)

    for field, value in update_data.items():
        setattr(conn, field, value)

    db.commit()
    db.refresh(conn)
    return _to_connection_read(conn)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    was_primary = conn.is_primary
    provider = conn.provider
    db.delete(conn)
    db.flush()

    if was_primary:
        replacement = (
            db.query(ProductivityConnection)
            .filter(
                ProductivityConnection.created_by_user_id == current_user.id,
                ProductivityConnection.provider == provider,
            )
            .order_by(ProductivityConnection.created_at.asc())
            .first()
        )
        if replacement:
            replacement.is_primary = True

    db.commit()


# --- Sync ---


@router.post("/connections/{connection_id}/sync", response_model=SyncResult)
def trigger_sync(
    connection_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    result = sync_connection(connection_id, db)
    return result


# --- Commits & PRs ---


@router.get("/connections/{connection_id}/commits", response_model=list[CommitRead])
def list_commits(
    connection_id: UUID,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    query = db.query(ProductivityCommit).filter(
        ProductivityCommit.connection_id == connection_id,
        ProductivityCommit.is_merge.is_(False),
    )

    if date_from:
        query = query.filter(ProductivityCommit.date >= date_from)
    if date_to:
        query = query.filter(ProductivityCommit.date < _end_of_day(date_to))

    return query.order_by(ProductivityCommit.date.desc()).all()


@router.get("/connections/{connection_id}/pull-requests", response_model=list[PullRequestRead])
def list_pull_requests(
    connection_id: UUID,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    query = db.query(ProductivityPullRequest).filter(
        ProductivityPullRequest.connection_id == connection_id
    )

    if date_from:
        query = query.filter(ProductivityPullRequest.created_at_remote >= date_from)
    if date_to:
        query = query.filter(ProductivityPullRequest.created_at_remote < _end_of_day(date_to))

    return query.order_by(ProductivityPullRequest.created_at_remote.desc()).all()


# --- Stats ---


@router.get("/connections/{connection_id}/stats", response_model=ConnectionStats)
def get_connection_stats(
    connection_id: UUID,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.id == connection_id,
            ProductivityConnection.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    commits_query = db.query(
        func.count(ProductivityCommit.id),
        func.coalesce(func.sum(ProductivityCommit.additions), 0),
        func.coalesce(func.sum(ProductivityCommit.deletions), 0),
    ).filter(
        ProductivityCommit.connection_id == connection_id,
        ProductivityCommit.is_merge.is_(False),
    )

    if date_from:
        commits_query = commits_query.filter(ProductivityCommit.date >= date_from)
    if date_to:
        commits_query = commits_query.filter(ProductivityCommit.date < _end_of_day(date_to))

    commits_count, total_additions, total_deletions = commits_query.one()

    prs_query = db.query(func.count(ProductivityPullRequest.id)).filter(
        ProductivityPullRequest.connection_id == connection_id
    )
    if date_from:
        prs_query = prs_query.filter(ProductivityPullRequest.created_at_remote >= date_from)
    if date_to:
        prs_query = prs_query.filter(ProductivityPullRequest.created_at_remote < _end_of_day(date_to))

    prs_count = prs_query.scalar()

    return ConnectionStats(
        connection_id=connection_id,
        commits_count=commits_count,
        prs_count=prs_count,
        total_additions=int(total_additions),
        total_deletions=int(total_deletions),
    )


@router.get("/stats", response_model=AggregatedStats)
def get_aggregated_stats(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    contract_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection_ids_query = db.query(ProductivityConnection.id).filter(
        ProductivityConnection.created_by_user_id == current_user.id
    )
    if contract_id:
        connection_ids_query = connection_ids_query.filter(
            ProductivityConnection.contract_id == contract_id
        )
    connection_ids = [row[0] for row in connection_ids_query.all()]

    if not connection_ids:
        return AggregatedStats(
            total_commits=0, total_prs=0, total_additions=0, total_deletions=0
        )

    commits_query = db.query(
        func.count(ProductivityCommit.id),
        func.coalesce(func.sum(ProductivityCommit.additions), 0),
        func.coalesce(func.sum(ProductivityCommit.deletions), 0),
    ).filter(
        ProductivityCommit.connection_id.in_(connection_ids),
        ProductivityCommit.is_merge.is_(False),
    )

    if date_from:
        commits_query = commits_query.filter(ProductivityCommit.date >= date_from)
    if date_to:
        commits_query = commits_query.filter(ProductivityCommit.date < _end_of_day(date_to))

    total_commits, total_additions, total_deletions = commits_query.one()

    prs_query = db.query(func.count(ProductivityPullRequest.id)).filter(
        ProductivityPullRequest.connection_id.in_(connection_ids)
    )
    if date_from:
        prs_query = prs_query.filter(ProductivityPullRequest.created_at_remote >= date_from)
    if date_to:
        prs_query = prs_query.filter(ProductivityPullRequest.created_at_remote < _end_of_day(date_to))

    total_prs = prs_query.scalar()

    return AggregatedStats(
        total_commits=total_commits,
        total_prs=total_prs,
        total_additions=int(total_additions),
        total_deletions=int(total_deletions),
    )


# --- User Activity (live GitHub) ---


@router.get("/user-activity", response_model=UserActivityResponse)
def get_user_activity(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.created_by_user_id == current_user.id,
            ProductivityConnection.provider == "github",
            ProductivityConnection.is_primary.is_(True),
        )
        .first()
    )
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No primary GitHub connection found. Mark one of your GitHub connections as primary first.",
        )

    try:
        from_dt = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        to_dt = (
            datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        ).replace(tzinfo=timezone.utc) - timedelta(seconds=1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from and date_to must be in YYYY-MM-DD format.",
        )

    pat = decrypt_value(conn.pat_encrypted)
    provider = GitHubProvider(pat=pat, username=conn.username)

    try:
        result = asyncio.run(provider.fetch_user_activity(from_dt, to_dt))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch GitHub activity: {exc}",
        )

    return UserActivityResponse(
        username=conn.username,
        date_from=date_from,
        date_to=date_to,
        totals=result["totals"],
        organizations=result["organizations"],
        diagnostics=result["diagnostics"],
    )
