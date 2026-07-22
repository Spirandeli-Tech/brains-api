"""Two-way Slack — turn an interpreted DM request into a tracked pipeline.

Flow (fase 4, mão dupla):
  DM → scheduler creates an ephemeral `/slack-dispatch` run (the LLM interpreter,
  runs on the runner) → the runner returns a fenced SLACK_ACTION json → this module
  (called from automation_service.update_automation_run when that run finishes)
  parses the decision, resolves the connection from the PR URL, launches the
  tracked pipeline (code_review / address_pr), and replies on the same DM.

Kept out of automation_service to avoid import cycles (this imports the launch
services + notifier). Everything is best-effort: a failure here must never break
the run-status patch that triggered it.
"""
from __future__ import annotations

import json
import logging
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.productivity_connection import ProductivityConnection
from app.services import address_pr_service, code_review_service, notifier

logger = logging.getLogger("slack.dispatch")

DISPATCH_SKILL = "/slack-dispatch"

_ACTION_RE = re.compile(r"```json\s+SLACK_ACTION\s*\n(.*?)```", re.DOTALL)
_URL_RE = re.compile(r"https?://(github\.com|bitbucket\.org)/([^/\s]+)/([^/\s?#]+)")


def resolve_connection_from_url(db: Session, url: str):
    """(connection, repo_name) for a PR URL, or (None, None) if unresolvable.

    Maps the URL owner/workspace to a stored ProductivityConnection by provider +
    workspace (case-insensitive) — the same connection the runner matches to its
    config.json by display_name."""
    if not url:
        return None, None
    m = _URL_RE.search(url)
    if not m:
        return None, None
    host, owner, repo = m.group(1), m.group(2), m.group(3)
    repo = repo[:-4] if repo.endswith(".git") else repo
    provider = "github" if "github" in host else "bitbucket"
    conn = (
        db.query(ProductivityConnection)
        .filter(
            ProductivityConnection.provider == provider,
            func.lower(ProductivityConnection.workspace) == owner.lower(),
        )
        .first()
    )
    return conn, repo


def _parse_action(result_summary: str | None) -> dict | None:
    if not result_summary:
        return None
    m = _ACTION_RE.search(result_summary)
    if not m:
        return None
    try:
        return json.loads(m.group(1).strip())
    except (ValueError, TypeError):
        return None


def handle_dispatch_completion(db: Session, automation, run) -> None:
    """Called when an ephemeral /slack-dispatch run reaches a terminal state.
    Parses the decision and either launches a tracked pipeline or just replies."""
    meta = automation.meta or {}
    channel = meta.get("slack_channel")
    thread_ts = meta.get("slack_ts")
    if not channel:
        return  # not a Slack-sourced dispatch

    def reply(text: str) -> None:
        notifier.post_reply(channel, text, thread_ts)

    if run.status == "failed":
        reply("⚠️ Não consegui interpretar o pedido (a análise falhou). Tenta de novo?")
        return

    action = _parse_action(run.result_summary)
    if not action:
        reply("🤔 Não entendi como uma ação. Manda de novo com o link do PR e o que "
              "você quer (ex.: “endereça os feedbacks desse PR <link>”).")
        return

    kind = (action.get("action") or "chat").strip()
    if kind == "chat":
        reply(action.get("reply") or "Beleza!")
        return

    pr_url = (action.get("pr_url") or "").strip()
    conn, repo_name = resolve_connection_from_url(db, pr_url)
    if conn is None:
        reply(f"Achei o pedido, mas não tenho conexão configurada pra `{pr_url or 'esse link'}`. "
              "Confere se a org está conectada no Brains.")
        return

    pr_number = code_review_service.pr_number_from_url(pr_url) or "?"
    try:
        if kind == "address_pr":
            if address_pr_service.has_active_run_for_pr(db, pr_url):
                reply(f"Já tem um address-PR ativo pro PR #{pr_number} em `{repo_name}` — não abri outro.")
                return
            address_pr_service.launch_run(
                db, user_id=automation.user_id, connection_id=conn.id,
                pr_url=pr_url, repo_name=repo_name,
            )
            reply(f"🛠️ Abrindo o *address-PR* do PR #{pr_number} em `{repo_name}` — "
                  "te aviso quando os fixes estiverem prontos pra revisar.")
        elif kind == "code_review":
            if code_review_service.has_active_run_for_pr(db, pr_url):
                reply(f"Já tem uma review ativa pro PR #{pr_number} em `{repo_name}` — não abri outra.")
                return
            code_review_service.launch_run(
                db, user_id=automation.user_id, connection_id=conn.id,
                pr_url=pr_url, repo_name=repo_name,
            )
            reply(f"🔍 Abrindo a *review* do PR #{pr_number} em `{repo_name}` — "
                  "te mando a review pra aprovar quando ficar pronta.")
        else:
            reply(action.get("reply") or f"Não sei tratar a ação “{kind}” ainda.")
    except Exception as e:  # noqa: BLE001
        logger.exception("slack dispatch launch failed")
        reply(f"⚠️ Deu ruim ao abrir o pipeline: {e}")
