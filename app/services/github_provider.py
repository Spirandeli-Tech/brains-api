import logging
from datetime import datetime

import httpx

from app.services.bitbucket_provider import is_merge_commit

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"

# Sentinel for "author id not resolved yet" so we can cache a genuine None result.
_UNSET = object()

# Pulls commit history with additions/deletions inline, so we no longer pay one
# extra REST request per commit for stats (the old per-commit crawl exhausted the
# GitHub rate limit and caused later repos in a sync to be skipped entirely).
COMMIT_HISTORY_QUERY = """
query($owner: String!, $name: String!, $expr: String!, $since: GitTimestamp, $cursor: String, $author: CommitAuthor) {
  repository(owner: $owner, name: $name) {
    object(expression: $expr) {
      ... on Commit {
        history(first: 100, since: $since, after: $cursor, author: $author) {
          pageInfo { hasNextPage endCursor }
          nodes {
            oid
            messageHeadline
            committedDate
            additions
            deletions
            author { name user { login } }
            parents { totalCount }
          }
        }
      }
    }
  }
}
"""


class GitHubAccessError(Exception):
    def __init__(self, status: int, message: str, sso_url: str | None = None):
        self.status = status
        self.message = message
        self.sso_url = sso_url
        super().__init__(message)


USER_CONTRIBUTIONS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      restrictedContributionsCount
      commitContributionsByRepository(maxRepositories: 100) {
        repository {
          nameWithOwner
          owner {
            login
            avatarUrl
          }
        }
        contributions {
          totalCount
        }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository {
          nameWithOwner
          owner {
            login
            avatarUrl
          }
        }
        contributions {
          totalCount
        }
      }
    }
  }
}
"""


class GitHubProvider:
    def __init__(self, pat: str, username: str, org: str | None = None):
        self.pat = pat
        self.username = username
        self.org = org
        self._author_id = _UNSET
        self.headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def validate_token(self) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/user", headers=self.headers)
            return resp.status_code == 200

    async def list_organizations(self) -> list[dict]:
        orgs: list[dict] = []
        async with httpx.AsyncClient() as client:
            page = 1
            while True:
                resp = await client.get(
                    f"{BASE_URL}/user/orgs",
                    headers=self.headers,
                    params={"per_page": 100, "page": page},
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                if not data:
                    break
                for org in data:
                    orgs.append({
                        "slug": org["login"],
                        "name": org.get("description") and f"{org['login']}" or org["login"],
                        "avatar_url": org.get("avatar_url"),
                        "description": org.get("description"),
                    })
                page += 1
        return orgs

    async def list_repositories(self) -> list[str]:
        repos: list[str] = []
        async with httpx.AsyncClient() as client:
            if self.org:
                url = f"{BASE_URL}/orgs/{self.org}/repos"
            else:
                url = f"{BASE_URL}/user/repos"

            page = 1
            while True:
                resp = await client.get(
                    url,
                    headers=self.headers,
                    params={"per_page": 100, "page": page},
                )
                if resp.status_code != 200:
                    body = resp.json() if resp.content else {}
                    gh_msg = body.get("message") if isinstance(body, dict) else None
                    sso_header = resp.headers.get("X-GitHub-SSO", "")
                    sso_url = None
                    if sso_header.startswith("required;"):
                        # Header format: "required; url=https://github.com/orgs/X/sso?..."
                        for p in (s.strip() for s in sso_header.split(";")):
                            if p.startswith("url="):
                                sso_url = p[4:]
                                break

                    if sso_url:
                        detail = (
                            f"Org '{self.org}' requires SAML SSO authorization"
                            f" for this token. Authorize at: {sso_url}"
                        )
                    elif gh_msg:
                        detail = gh_msg
                    elif self.org:
                        detail = (
                            f"GitHub returned {resp.status_code} listing repos for"
                            f" '{self.org}'. The token likely lacks access"
                            " (classic PAT disabled, fine-grained PAT not approved,"
                            " or missing scopes)."
                        )
                    else:
                        detail = f"GitHub returned {resp.status_code}: {resp.text[:200]}"

                    logger.warning(
                        f"GitHub list repos failed: status={resp.status_code} url={url} msg={gh_msg}"
                    )
                    raise GitHubAccessError(resp.status_code, detail, sso_url)

                data = resp.json()
                if not data:
                    break

                for repo in data:
                    repos.append(repo["full_name"])
                page += 1

        if not repos and self.org:
            raise GitHubAccessError(
                200,
                f"GitHub returned an empty repo list for org '{self.org}'."
                " The token sees the org but has no repos approved for it"
                " (typical when the org restricts classic PATs to specific repos,"
                " or the token's SAML SSO authorization is missing).",
            )
        return repos

    async def list_branches(self, repo: str) -> list[str]:
        branches: list[str] = []
        async with httpx.AsyncClient() as client:
            page = 1
            while True:
                resp = await client.get(
                    f"{BASE_URL}/repos/{repo}/branches",
                    headers=self.headers,
                    params={"per_page": 100, "page": page},
                )
                if resp.status_code != 200:
                    logger.warning(
                        f"GitHub list branches failed for {repo}: {resp.status_code}"
                    )
                    break
                data = resp.json()
                if not data:
                    break
                for b in data:
                    branches.append(b["name"])
                page += 1
        return branches

    async def _graphql(
        self, client: httpx.AsyncClient, query: str, variables: dict
    ) -> dict:
        resp = await client.post(
            GRAPHQL_URL,
            headers={**self.headers, "Content-Type": "application/json"},
            json={"query": query, "variables": variables},
        )
        # Primary/secondary rate limits surface as HTTP 403/429; stop the sync
        # cleanly so the caller can mark the connection rate-limited.
        if resp.status_code in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            raise GitHubAccessError(
                resp.status_code,
                f"GitHub GraphQL rate limit hit; "
                f"remaining={remaining}, reset_epoch={reset}",
            )
        resp.raise_for_status()
        payload = resp.json()
        # GraphQL can also report exhaustion as a 200 with a RATE_LIMITED error.
        for err in payload.get("errors") or []:
            if err.get("type") == "RATE_LIMITED":
                raise GitHubAccessError(
                    403, f"GitHub GraphQL rate limited: {err.get('message')}"
                )
        return payload

    async def _resolve_author_id(self, client: httpx.AsyncClient) -> str | None:
        """Resolve the GraphQL node id for self.username once, so commit history
        can be filtered server-side by author. Falls back to None (client-side
        login matching) if it can't be resolved."""
        if self._author_id is not _UNSET:
            return self._author_id
        try:
            payload = await self._graphql(
                client,
                "query($login: String!) { user(login: $login) { id } }",
                {"login": self.username},
            )
            user = (payload.get("data") or {}).get("user") or {}
            self._author_id = user.get("id")
        except GitHubAccessError:
            raise
        except Exception as e:
            logger.warning(f"Could not resolve author id for {self.username}: {e}")
            self._author_id = None
        return self._author_id

    async def fetch_commits(
        self, repo: str, since: datetime | None = None
    ) -> list[dict]:
        owner, _, name = repo.partition("/")
        commits: list[dict] = []
        seen: set[str] = set()
        branches = await self.list_branches(repo)
        if not branches:
            branches = [""]

        since_iso = since.isoformat() if since else None

        async with httpx.AsyncClient(timeout=30.0) as client:
            author_id = await self._resolve_author_id(client)
            author_filter = {"id": author_id} if author_id else None

            for branch in branches:
                expr = branch if branch else "HEAD"
                cursor: str | None = None
                while True:
                    payload = await self._graphql(
                        client,
                        COMMIT_HISTORY_QUERY,
                        {
                            "owner": owner,
                            "name": name,
                            "expr": expr,
                            "since": since_iso,
                            "cursor": cursor,
                            "author": author_filter,
                        },
                    )
                    obj = ((payload.get("data") or {}).get("repository") or {}).get("object")
                    if not obj:
                        break
                    history = obj.get("history") or {}
                    nodes = history.get("nodes") or []

                    for node in nodes:
                        sha = node["oid"]
                        if sha in seen:
                            continue
                        # Without a resolved author id we filter client-side by login.
                        if not author_id:
                            login = ((node.get("author") or {}).get("user") or {}).get("login")
                            if login != self.username:
                                continue
                        seen.add(sha)
                        parent_count = (node.get("parents") or {}).get("totalCount", 0)
                        headline = node.get("messageHeadline") or ""
                        commits.append({
                            "hash": sha,
                            "short_hash": sha[:7],
                            "message": headline.split("\n")[0],
                            "author": (node.get("author") or {}).get("name") or self.username,
                            "date": node["committedDate"],
                            "additions": node.get("additions", 0),
                            "deletions": node.get("deletions", 0),
                            "repository": repo,
                            "is_merge": is_merge_commit([None] * parent_count, headline),
                        })

                    page_info = history.get("pageInfo") or {}
                    if not page_info.get("hasNextPage"):
                        break
                    cursor = page_info.get("endCursor")

        return commits

    async def fetch_user_activity(
        self, date_from: datetime, date_to: datetime
    ) -> dict:
        variables = {
            "login": self.username,
            "from": date_from.isoformat().replace("+00:00", "Z"),
            "to": date_to.isoformat().replace("+00:00", "Z"),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GRAPHQL_URL,
                headers={**self.headers, "Content-Type": "application/json"},
                json={"query": USER_CONTRIBUTIONS_QUERY, "variables": variables},
            )
            resp.raise_for_status()
            payload = resp.json()

        if payload.get("errors"):
            raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")

        user_data = (payload.get("data") or {}).get("user")
        if not user_data:
            return {
                "organizations": [],
                "totals": {"commits": 0, "prs": 0},
                "diagnostics": {
                    "github_total_commits": 0,
                    "github_total_prs": 0,
                    "restricted_contributions": 0,
                },
            }

        collection = user_data.get("contributionsCollection", {}) or {}
        orgs: dict[str, dict] = {}

        def _ensure_org(owner: dict) -> dict:
            login = owner["login"]
            if login not in orgs:
                orgs[login] = {
                    "login": login,
                    "avatar_url": owner.get("avatarUrl"),
                    "commits": 0,
                    "prs": 0,
                    "repositories": {},
                }
            return orgs[login]

        def _ensure_repo(org: dict, name_with_owner: str) -> dict:
            if name_with_owner not in org["repositories"]:
                org["repositories"][name_with_owner] = {
                    "name_with_owner": name_with_owner,
                    "commits": 0,
                    "prs": 0,
                }
            return org["repositories"][name_with_owner]

        for entry in collection.get("commitContributionsByRepository") or []:
            repo = entry["repository"]
            count = entry["contributions"]["totalCount"]
            org = _ensure_org(repo["owner"])
            repo_agg = _ensure_repo(org, repo["nameWithOwner"])
            repo_agg["commits"] += count
            org["commits"] += count

        for entry in collection.get("pullRequestContributionsByRepository") or []:
            repo = entry["repository"]
            count = entry["contributions"]["totalCount"]
            org = _ensure_org(repo["owner"])
            repo_agg = _ensure_repo(org, repo["nameWithOwner"])
            repo_agg["prs"] += count
            org["prs"] += count

        organizations = []
        total_commits = 0
        total_prs = 0
        for org in orgs.values():
            repos = sorted(
                org["repositories"].values(),
                key=lambda r: (r["commits"] + r["prs"]),
                reverse=True,
            )
            organizations.append({
                "login": org["login"],
                "avatar_url": org["avatar_url"],
                "commits": org["commits"],
                "prs": org["prs"],
                "repositories": repos,
            })
            total_commits += org["commits"]
            total_prs += org["prs"]

        organizations.sort(key=lambda o: (o["commits"] + o["prs"]), reverse=True)

        return {
            "organizations": organizations,
            "totals": {"commits": total_commits, "prs": total_prs},
            "diagnostics": {
                "github_total_commits": collection.get("totalCommitContributions", 0),
                "github_total_prs": collection.get("totalPullRequestContributions", 0),
                "restricted_contributions": collection.get("restrictedContributionsCount", 0),
            },
        }

    async def fetch_pull_requests(
        self, repo: str, since: datetime | None = None
    ) -> list[dict]:
        prs: list[dict] = []
        params: dict = {"state": "all", "per_page": 100, "sort": "updated", "direction": "desc"}

        async with httpx.AsyncClient() as client:
            page = 1
            while True:
                params["page"] = page
                resp = await client.get(
                    f"{BASE_URL}/repos/{repo}/pulls",
                    headers=self.headers,
                    params=params,
                )
                if resp.status_code in (403, 429):
                    remaining = resp.headers.get("X-RateLimit-Remaining")
                    reset = resp.headers.get("X-RateLimit-Reset")
                    raise GitHubAccessError(
                        resp.status_code,
                        f"GitHub rate limit hit while listing PRs for {repo}; "
                        f"remaining={remaining}, reset_epoch={reset}",
                    )
                if resp.status_code != 200:
                    break

                data = resp.json()
                if not data:
                    break

                for item in data:
                    if item["user"]["login"] != self.username:
                        continue

                    created_at = datetime.fromisoformat(
                        item["created_at"].replace("Z", "+00:00")
                    )
                    if since and created_at < since:
                        continue

                    merged_at = None
                    if item.get("merged_at"):
                        merged_at = item["merged_at"]

                    status = "open"
                    if item.get("merged_at"):
                        status = "merged"
                    elif item["state"] == "closed":
                        status = "closed"

                    prs.append({
                        "number": item["number"],
                        "title": item["title"],
                        "status": status,
                        "repository": repo,
                        "url": item["html_url"],
                        "created_at_remote": item["created_at"],
                        "merged_at": merged_at,
                    })

                if since:
                    last_updated = datetime.fromisoformat(
                        data[-1]["updated_at"].replace("Z", "+00:00")
                    )
                    if last_updated < since:
                        break

                page += 1

        return prs
