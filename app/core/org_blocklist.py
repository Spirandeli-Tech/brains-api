"""Hard block on one organisation the platform must never touch again.

Access to that client was revoked, so Brains must hold none of its data and
must never act on its behalf — no runs, no watchers, no automations, no
invoices, nothing. The rule is enforced in layers, and each layer fails loudly
rather than silently dropping the request:

  1. this module's ASGI middleware, on every inbound HTTP request;
  2. the database triggers installed by `install_db_guard`, so even a direct
     SQL write is rejected;
  3. `runner/org_blocklist.py`, on the host side that actually runs jobs;
  4. `.claude/hooks/org-blocklist.py`, on Claude Code tool calls in this repo.

Anything matching `BLOCKED_RE` is refused. Keep the pattern here in sync with
the runner and hook copies — they are deliberate duplicates, because the three
processes share no code.
"""

import json
import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Case-insensitive: org name and its spellings, its repos, its branch names.
# The ticket-key pattern is matched case-sensitively and needs 3+ digits, so
# ordinary dates ("Nov-25") do not trip it.
BLOCKED_RE = re.compile(
    r"novo[\s_-]?ed|novoedweb|venture[\s_-]?shell|origami_(?:develop|master)",
    re.IGNORECASE,
)
TICKET_RE = re.compile(r"\bNOV-\d{3,}\b")

MESSAGE = (
    "Blocked: this platform is permanently barred from the NovoEd organisation. "
    "Nothing related to it may be stored, queried or acted upon."
)


class OrgBlocked(Exception):
    """Raised when a blocked organisation is referenced."""

    def __init__(self, term: str) -> None:
        self.term = term
        super().__init__(f"{MESSAGE} (matched: {term!r})")


def find_blocked(text: str | None) -> str | None:
    """Return the offending substring, or None when the text is clean."""
    if not text:
        return None
    m = BLOCKED_RE.search(text) or TICKET_RE.search(text)
    return m.group(0) if m else None


def assert_allowed(*values: object) -> None:
    """Raise OrgBlocked if any value mentions the blocked organisation."""
    for value in values:
        if value is None:
            continue
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        term = find_blocked(text)
        if term:
            raise OrgBlocked(term)


class OrgBlocklistMiddleware:
    """Reject any request whose path, query or body references the blocked org.

    Written as raw ASGI rather than BaseHTTPMiddleware so the body can be
    buffered for inspection and then replayed to the app untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        target = scope.get("path", "") + "?" + (scope.get("query_string", b"").decode("latin-1"))
        term = find_blocked(target)

        body = b""
        if term is None:
            more = True
            while more:
                message = await receive()
                if message["type"] == "http.request":
                    body += message.get("body", b"")
                    more = message.get("more_body", False)
                else:  # http.disconnect
                    more = False
            term = find_blocked(body.decode("utf-8", "replace"))

        if term is not None:
            await self._reject(send, term)
            return

        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send: Send, term: str) -> None:
        payload = json.dumps({"detail": f"{MESSAGE} (matched: {term!r})"}).encode()
        await send({
            "type": "http.response.start",
            "status": 451,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": payload})


# Tables that carry org-identifying data. A BEFORE INSERT OR UPDATE trigger on
# each one rejects the write, so the block survives a bypass of the API.
GUARDED_TABLES = (
    "customers", "contracts", "contract_services", "invoices", "invoice_services",
    "productivity_connections", "productivity_commits", "productivity_pull_requests",
    "automations", "automation_runs", "watchers", "watcher_sightings",
    "implementation_runs", "implementation_steps",
    "code_review_runs", "code_review_steps",
    "address_pr_runs", "address_pr_steps",
    "planner_runs", "platform_events", "proposals", "local_commits",
    "recurring_tasks", "ideas", "task_executions", "user_git_emails",
)

# POSIX equivalents of BLOCKED_RE / TICKET_RE above.
_PG_PATTERN = r"novo[[:space:]_-]?ed|novoedweb|venture[[:space:]_-]?shell|origami_(develop|master)"
_PG_TICKET = r"NOV-[0-9]{3,}"

_GUARD_FN = f"""
CREATE OR REPLACE FUNCTION brains_org_blocklist() RETURNS trigger AS $fn$
DECLARE
  row_text text := to_jsonb(NEW)::text;
BEGIN
  IF row_text ~* '{_PG_PATTERN}' OR row_text ~ '{_PG_TICKET}' THEN
    RAISE EXCEPTION
      'Blocked organisation referenced in %, write rejected', TG_TABLE_NAME
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;
"""


def install_db_guard(engine) -> None:
    """Create (or refresh) the blocking triggers. Idempotent; safe on every boot."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(_GUARD_FN))
        existing = {
            row[0]
            for row in conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            ))
        }
        for table in GUARDED_TABLES:
            if table not in existing:
                continue
            conn.execute(text(f'DROP TRIGGER IF EXISTS trg_org_blocklist ON "{table}"'))
            conn.execute(text(
                f'CREATE TRIGGER trg_org_blocklist BEFORE INSERT OR UPDATE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION brains_org_blocklist()"
            ))
