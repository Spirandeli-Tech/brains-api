from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


VALID_PROVIDERS = ("github", "bitbucket")


class ValidateTokenRequest(BaseModel):
    provider: str
    pat: str
    username: str

    @field_validator("provider")
    @classmethod
    def provider_must_be_valid(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {VALID_PROVIDERS}")
        return v


class OrganizationInfo(BaseModel):
    slug: str
    name: str
    avatar_url: str | None = None
    description: str | None = None


class ValidateTokenResponse(BaseModel):
    valid: bool
    organizations: list[OrganizationInfo]


class ConnectionCreate(BaseModel):
    provider: str
    pat: str
    username: str
    workspace: str | None = None
    contract_id: UUID | None = None
    custom_name: str | None = None
    selected_repos: list[str] | None = None
    is_primary: bool = False

    @field_validator("provider")
    @classmethod
    def provider_must_be_valid(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {VALID_PROVIDERS}")
        return v

    @model_validator(mode="after")
    def name_or_contract_required(self):
        if not self.contract_id and not self.custom_name:
            raise ValueError("Either contract_id or custom_name must be provided")
        return self


class ConnectionUpdate(BaseModel):
    pat: str | None = None
    username: str | None = None
    workspace: str | None = None
    contract_id: UUID | None = None
    custom_name: str | None = None
    selected_repos: list[str] | None = None
    is_primary: bool | None = None


class ConnectionRead(BaseModel):
    id: UUID
    provider: str
    username: str
    workspace: str | None
    contract_id: UUID | None
    custom_name: str | None
    display_name: str
    pat_masked: str
    selected_repos: list[str] | None
    is_primary: bool
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConnectionListItem(BaseModel):
    id: UUID
    provider: str
    display_name: str
    username: str
    workspace: str | None
    contract_id: UUID | None
    selected_repos: list[str] | None
    is_primary: bool
    last_synced_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class CommitRead(BaseModel):
    id: UUID
    hash: str
    short_hash: str
    message: str
    author: str
    date: datetime
    additions: int
    deletions: int
    repository: str
    pr_number: int | None
    pr_url: str | None

    class Config:
        from_attributes = True


class PullRequestRead(BaseModel):
    id: UUID
    number: int
    title: str
    status: str
    repository: str
    url: str
    created_at_remote: datetime
    merged_at: datetime | None

    class Config:
        from_attributes = True


class ConnectionStats(BaseModel):
    connection_id: UUID
    commits_count: int
    prs_count: int
    total_additions: int
    total_deletions: int


class AggregatedStats(BaseModel):
    total_commits: int
    total_prs: int
    total_additions: int
    total_deletions: int


class SyncResult(BaseModel):
    connection_id: UUID
    status: str  # "started" | "in_progress" | "completed"
    commits_synced: int = 0
    prs_synced: int = 0
    errors: list[str] = []


class UserActivityRepo(BaseModel):
    name_with_owner: str
    commits: int
    prs: int


class UserActivityOrg(BaseModel):
    login: str
    avatar_url: str | None = None
    commits: int
    prs: int
    repositories: list[UserActivityRepo]


class UserActivityTotals(BaseModel):
    commits: int
    prs: int


class UserActivityDiagnostics(BaseModel):
    github_total_commits: int
    github_total_prs: int
    restricted_contributions: int


class UserActivityResponse(BaseModel):
    username: str
    date_from: str
    date_to: str
    totals: UserActivityTotals
    organizations: list[UserActivityOrg]
    diagnostics: UserActivityDiagnostics


class GitEmailCreate(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not v or "@" not in v:
            raise ValueError("invalid email")
        return v


class GitEmailRead(BaseModel):
    id: UUID
    email: str
    created_at: datetime

    class Config:
        from_attributes = True
