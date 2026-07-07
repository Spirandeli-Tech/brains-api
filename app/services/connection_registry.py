"""Registry of runner-side connections (orgs) and their repos.

The API is the control plane; the host runner is the execution plane. The
runner owns the real source of truth (its local config.json), and pushes a
read-only snapshot here on startup via PUT /implementations/runner/repos so
the UI can render org/repo pickers without ever seeing local filesystem
paths. Shared by the Implementations and Automations features.

In-memory and re-populated on every runner restart — acceptable for a local
single-runner setup.
"""

_connections: dict[str, list[dict]] = {}


def register_repos(connection_name: str, repos: list[dict]) -> None:
    _connections[connection_name] = repos


def get_repos_for_connection(connection_name: str) -> list[dict]:
    return _connections.get(connection_name, [])


def list_connections() -> list[dict]:
    return [{"name": name, "repos": repos} for name, repos in _connections.items()]
