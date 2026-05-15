from datetime import datetime
from typing import Protocol


class GitProviderClient(Protocol):
    async def validate_token(self) -> bool: ...

    async def list_repositories(self) -> list[str]: ...

    async def fetch_commits(
        self, repo: str, since: datetime | None = None
    ) -> list[dict]: ...

    async def fetch_pull_requests(
        self, repo: str, since: datetime | None = None
    ) -> list[dict]: ...
