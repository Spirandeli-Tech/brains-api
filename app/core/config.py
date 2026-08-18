from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    FIREBASE_SERVICE_ACCOUNT_PATH: str = ""
    CORS_ORIGINS: str = "http://localhost:5173"
    ENCRYPTION_KEY: str = ""
    # Shared secret the host-side implementation runner presents (X-Runner-Token)
    # to claim runs and patch status. Empty disables the runner endpoints.
    RUNNER_TOKEN: str = ""
    # conexões da fábrica de agentes: steps de implementação nunca pausam para
    # aprovação (gates humanos são só dinheiro/publicação/legal). Display names
    # separados por vírgula.
    AUTONOMOUS_CONNECTIONS: str = ""
    # Read-only mount of the host's ~/.claude, used to discover available skills for automations.
    CLAUDE_HOME_DIR: str = "/root/.claude"
    # Slack notifier (proactive platform fase 3). Both empty disables it — the
    # notifier no-ops, so the platform runs fine without Slack configured.
    SLACK_BOT_TOKEN: str = ""
    SLACK_USER_ID: str = ""
    # App-level token (xapp-…, scope connections:write) for Socket Mode — lets the
    # scheduler receive interactive button clicks (approve/discard) with no public
    # URL. Empty disables the interactive listener; text messages still work.
    SLACK_APP_TOKEN: str = ""
    # Per-category channel routing (fase 3.1). Each holds a Slack channel id
    # (e.g. "C0123ABCD") the bot has been invited to. Any left empty falls back
    # to the operator DM (SLACK_USER_ID), so partial config just routes the
    # channels you set and DMs the rest — matching the pre-routing behaviour.
    SLACK_CHANNEL_APPROVALS: str = ""     # awaiting_approval + proposal_created
    SLACK_CHANNEL_CODE_REVIEW: str = ""   # code-review runs finished
    SLACK_CHANNEL_FAILURES: str = ""      # run_failed (any source)
    SLACK_CHANNEL_DIGEST: str = ""        # daily morning digest
    SLACK_CHANNEL_EMPRESA: str = ""       # feed da empresa de agentes (agent_message)
    # Base URL of the web UI, used to build deep links in Slack messages.
    WEB_BASE_URL: str = "http://localhost:3737"
    # Read-only mounts for the devocionais listing — the skills write directly to
    # these paths on the host; the API only ever reads them, never writes.
    DEVOCIONAL_CONTENT_DIR: str = "/data/devocional-content"
    DEVOCIONAL_VIDEOS_DIR: str = "/data/devocional-videos"
    DEVOCIONAL_LEDGER_PATH: str = "/data/kdp/devocional-sent.json"
    # Google Generative Language API key — drafts the "cola" (recording cue)
    # from a script's body. Empty disables the /topics/generate endpoint.
    GEMINI_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields like POSTGRES_USER, POSTGRES_PASSWORD, etc.

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


settings = Settings()
