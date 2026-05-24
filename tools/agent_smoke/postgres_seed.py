"""Seed Customer + Identity + Membership rows into gateway's postgres.

Gateway's provision endpoint refuses unknown customers (`coke_account_not_found`),
so for synthetic smoke accounts we have to seed the platform identity graph
directly. No public registration API exists for test users.

Reads the DB URL from `SMOKE_GATEWAY_DB_URL` env var, falling back to
`gateway/.env`'s `DATABASE_URL`, then to the dev default.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_URL = "postgresql://clawscale:clawscale@127.0.0.1:15432/clawscale"


@dataclass
class _ParsedDsn:
    host: str
    port: str
    user: str
    password: str | None
    dbname: str


def _read_database_url() -> str:
    env_url = os.environ.get("SMOKE_GATEWAY_DB_URL")
    if env_url:
        return env_url
    dotenv_path = PROJECT_ROOT / "gateway" / ".env"
    if dotenv_path.exists():
        for raw in dotenv_path.read_text().splitlines():
            line = raw.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return DEFAULT_DB_URL


def _parse(url: str) -> _ParsedDsn:
    parts = urlsplit(url)
    return _ParsedDsn(
        host=parts.hostname or "127.0.0.1",
        port=str(parts.port or 5432),
        user=parts.username or "postgres",
        password=parts.password,
        dbname=(parts.path or "/postgres").lstrip("/").split("?", 1)[0],
    )


def _run_psql(sql: str) -> str:
    dsn = _parse(_read_database_url())
    env = os.environ.copy()
    if dsn.password:
        env["PGPASSWORD"] = dsn.password
    cmd = [
        "psql",
        "-h", dsn.host,
        "-p", dsn.port,
        "-U", dsn.user,
        "-d", dsn.dbname,
        "-v", "ON_ERROR_STOP=1",
        "-X",
        "-A",
        "-t",
        "-c", sql,
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"psql failed: cmd={shlex.join(cmd)} stderr={result.stderr.strip()}"
        )
    return result.stdout


def seed_customer_graph(
    *,
    coke_account_id: str,
    identity_id: str,
    email: str,
    display_name: str,
) -> None:
    """Insert Customer + Identity + Membership rows, idempotent."""
    safe_display = display_name.replace("'", "''")
    safe_email = email.replace("'", "''")
    sql = f"""
INSERT INTO identities (id, email, display_name, claim_status, updated_at)
VALUES ('{identity_id}', '{safe_email}', '{safe_display}', 'active', NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO customers (id, kind, display_name, updated_at)
VALUES ('{coke_account_id}', 'personal', '{safe_display}', NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO memberships (id, identity_id, customer_id, role, updated_at)
VALUES ('mem_{identity_id}_{coke_account_id}', '{identity_id}', '{coke_account_id}', 'owner', NOW())
ON CONFLICT (id) DO NOTHING;
"""
    _run_psql(sql)
