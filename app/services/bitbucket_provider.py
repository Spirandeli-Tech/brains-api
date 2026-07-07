import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bitbucket.org/2.0"

_MERGE_MESSAGE_PREFIXES = ("Merge ", "Merged ")


def is_merge_commit(parents: list | None, message: str | None) -> bool:
    """Detect merge commits even when squash/fast-forward strategies hide them
    behind a single parent (common in Bitbucket UI merges)."""
    if parents and len(parents) > 1:
        return True
    if message:
        first_line = message.split("\n", 1)[0]
        if first_line.startswith(_MERGE_MESSAGE_PREFIXES):
            return True
    return False


class BitbucketProvider:
    def __init__(
        self,
        pat: str,
        username: str,
        workspace: str | None = None,
        external_account_id: str | None = None,
    ):
        self.username = username
        self.workspace = workspace or username
        self.pat = pat
        self.external_account_id = external_account_id

    async def validate_token(self) -> bool:
        """Confirm the PAT/username combo authenticates successfully.

        Bitbucket deprecated every cross-workspace listing endpoint for
        API-token auth (CHANGE-2770) — `/repositories?role=member` and bare
        `/workspaces`/`/repositories` all now return 410 regardless of PAT
        validity, which used to make this always report "invalid" even for
        a working token. `/user` doesn't have that problem: a 401 means the
        credentials themselves are wrong, while a 403 here means Bitbucket
        authenticated the request but is enforcing a scope restriction on
        it — i.e. the credentials ARE valid, per plain HTTP semantics.
        """
        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            resp = await client.get(f"{BASE_URL}/user")
            return resp.status_code in (200, 403)

    def _client_kwargs(self) -> dict:
        return {"auth": httpx.BasicAuth(self.username, self.pat)}

    async def get_current_user(self) -> dict | None:
        """Fetch the account that owns the PAT. Returns None on failure.
        Bitbucket's `username` field is deprecated (GDPR); `nickname` is the
        public handle and `account_id` is the stable opaque identifier."""
        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            resp = await client.get(f"{BASE_URL}/user")
            if resp.status_code != 200:
                return None
            data = resp.json()
            return {
                "account_id": data.get("account_id"),
                "uuid": data.get("uuid"),
                "nickname": data.get("nickname"),
                "display_name": data.get("display_name"),
                "username": data.get("username"),
            }

    async def list_workspaces(self) -> list[dict]:
        workspaces: list[dict] = []

        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            # Try /workspaces first
            resp = await client.get(f"{BASE_URL}/workspaces", params={"pagelen": 100})
            if resp.status_code == 200:
                data = resp.json()
                for ws in data.get("values", []):
                    avatar_url = ws.get("links", {}).get("avatar", {}).get("href")
                    workspaces.append({
                        "slug": ws["slug"],
                        "name": ws.get("name", ws["slug"]),
                        "avatar_url": avatar_url,
                        "description": None,
                    })
                return workspaces

            # Fall back: extract unique workspaces from repositories
            seen: set[str] = set()
            url: str | None = f"{BASE_URL}/repositories"
            params: dict = {"pagelen": 100, "role": "member"}
            while url:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    break
                data = resp.json()
                for repo in data.get("values", []):
                    ws = repo.get("workspace", {})
                    slug = ws.get("slug", "")
                    if slug and slug not in seen:
                        seen.add(slug)
                        avatar_url = ws.get("links", {}).get("avatar", {}).get("href")
                        workspaces.append({
                            "slug": slug,
                            "name": ws.get("name", slug),
                            "avatar_url": avatar_url,
                            "description": None,
                        })
                url = data.get("next")
                params = {}

        return workspaces

    async def list_repositories(self) -> list[str]:
        repos: list[str] = []
        url: str | None = f"{BASE_URL}/repositories/{self.workspace}"

        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            while url:
                resp = await client.get(url, params={"pagelen": 100})
                if resp.status_code != 200:
                    logger.warning(f"Bitbucket list repos failed: {resp.status_code}")
                    break

                data = resp.json()
                for repo in data.get("values", []):
                    repos.append(f"{self.workspace}/{repo['slug']}")

                url = data.get("next")

        return repos

    def _is_self_author(self, author_user: dict) -> bool:
        """`author_user` is the Bitbucket user object — nickname/username/
        display_name/account_id. Shape differs by endpoint: commits nest it
        under `author.user`, pull requests put it directly on `author` — the
        caller resolves that before calling this."""
        # Prefer account_id (stable, unambiguous) when the connection has it.
        if self.external_account_id:
            return author_user.get("account_id") == self.external_account_id
        # Legacy path for connections created before account_id capture.
        candidates = {
            author_user.get("nickname"),
            author_user.get("username"),
            author_user.get("display_name"),
            author_user.get("account_id"),
        }
        return self.username in {c for c in candidates if c}

    async def _get_main_branch(self, client: httpx.AsyncClient, repo: str) -> str | None:
        resp = await client.get(f"{BASE_URL}/repositories/{repo}")
        if resp.status_code != 200:
            return None
        return (resp.json().get("mainbranch") or {}).get("name")

    async def fetch_commits(
        self, repo: str, since: datetime | None = None
    ) -> list[dict]:
        """Crawl the repo's main branch only.

        Bitbucket has no server-side author/date filter for commits (unlike
        the GitHub provider's GraphQL query), so every branch scanned here
        costs a full paginated commits crawl plus a diffstat call per
        matched commit. Real repos routinely carry 100+ stale per-ticket
        branches (a `refs/branches?pagelen=1` probe on one repo in this
        codebase reported 196) — iterating all of them, as this used to do,
        multiplies that cost per branch and was the actual cause of syncs
        that appeared to hang. Once a branch merges, its commits reach the
        main branch anyway (same hash unless squashed), so scoping to just
        the main branch is both far cheaper and a more accurate picture of
        shipped work than counting commits still stuck on abandoned branches.
        """
        commits: list[dict] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            branch = await self._get_main_branch(client, repo)
            url: str | None = (
                f"{BASE_URL}/repositories/{repo}/commits/{branch}"
                if branch
                else f"{BASE_URL}/repositories/{repo}/commits"
            )

            stop = False
            params: dict = {"pagelen": 100}
            while url:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        f"Bitbucket fetch commits failed for {repo}@{branch or 'default'}: "
                        f"{resp.status_code}"
                    )
                    break

                data = resp.json()

                for item in data.get("values", []):
                    commit_date = datetime.fromisoformat(
                        item["date"].replace("Z", "+00:00")
                    )
                    if since and commit_date < since:
                        stop = True
                        break

                    author_raw = item.get("author", {})
                    author_user = author_raw.get("user", {}) or {}
                    if not self._is_self_author(author_user):
                        continue

                    sha = item["hash"]
                    if sha in seen:
                        continue
                    seen.add(sha)

                    author_name = (
                        author_user.get("display_name")
                        or author_raw.get("raw", "unknown").split("<")[0].strip()
                    )

                    diffstat = await self._get_diffstat(client, repo, sha)

                    commits.append({
                        "hash": sha,
                        "short_hash": sha[:7],
                        "message": item.get("message", "").split("\n")[0],
                        "author": author_name,
                        "date": item["date"],
                        "additions": diffstat["additions"],
                        "deletions": diffstat["deletions"],
                        "repository": repo,
                        "is_merge": is_merge_commit(
                            item.get("parents"), item.get("message")
                        ),
                    })

                if stop:
                    break
                url = data.get("next")
                params = {}

        return commits

    async def _get_diffstat(
        self, client: httpx.AsyncClient, repo: str, sha: str
    ) -> dict:
        additions = 0
        deletions = 0
        url: str | None = f"{BASE_URL}/repositories/{repo}/diffstat/{sha}"

        while url:
            resp = await client.get(url)
            if resp.status_code != 200:
                break

            data = resp.json()
            for entry in data.get("values", []):
                additions += entry.get("lines_added", 0)
                deletions += entry.get("lines_removed", 0)

            url = data.get("next")

        return {"additions": additions, "deletions": deletions}

    async def fetch_pull_requests(
        self, repo: str, since: datetime | None = None
    ) -> list[dict]:
        prs: list[dict] = []
        url: str | None = f"{BASE_URL}/repositories/{repo}/pullrequests"
        # Sort newest-first so the `since` cutoff below can stop paging early —
        # without it, this walked the repo's ENTIRE pull request history on
        # every sync (no early exit existed at all).
        params: dict = {"pagelen": 50, "state": "MERGED,OPEN,DECLINED", "sort": "-created_on"}

        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            stop = False
            while url:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    break

                data = resp.json()
                for item in data.get("values", []):
                    created_at = datetime.fromisoformat(
                        item["created_on"].replace("Z", "+00:00")
                    )
                    if since and created_at < since:
                        stop = True
                        break

                    if not self._is_self_author(item.get("author", {}) or {}):
                        continue

                    status_map = {
                        "OPEN": "open",
                        "MERGED": "merged",
                        "DECLINED": "declined",
                        "SUPERSEDED": "closed",
                    }

                    merged_at = None
                    if item.get("updated_on") and item["state"] == "MERGED":
                        merged_at = item["updated_on"]

                    prs.append({
                        "number": item["id"],
                        "title": item["title"],
                        "status": status_map.get(item["state"], "open"),
                        "repository": repo,
                        "url": item["links"]["html"]["href"],
                        "created_at_remote": item["created_on"],
                        "merged_at": merged_at,
                    })

                url = data.get("next")
                params = {}

        return prs
