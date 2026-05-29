# Coke Clean Rebuild Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the first clean-rebuild Python backend package foundation with typed configuration, Flask app construction, lazy Postgres and Redis factories, immutable outbox event values, and W3C traceparent helpers.

**Architecture:** This slice creates infrastructure seams only. The `coke` package must stand alone from legacy `dao`, `connector`, and `gateway` modules while preparing for the settled ingress/egress tier, worker tier, Postgres durable state, Redis coordination, single transactional outbox, and trace propagation contract. It intentionally stops before schemas, domain modules, workers, provider adapters, scheduler code, Alembic revisions, and web work.

**Tech Stack:** Python 3.12, Flask 3.1, Pydantic v2 already present for later settings/domain work, SQLAlchemy 2.x, Alembic, psycopg 3, Redis 5, OpenTelemetry API/SDK, pytest.

---

**Plan Status:** draft
**Status Date:** 2026-05-29
**Parent Plan:** `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`, Task 2: Backend Package And Infrastructure Foundation
**Source Specs:**
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`

**Freshness Check:** Before executing, verify this plan against current `main`, `docs/ARCHITECTURE.md`, `docs/design-docs/coke-working-contract.md`, and the target architecture spec. The clean-rebuild contract at the time this plan was written is: Python backend split into ingress/egress and worker tiers, thin Next.js client, Postgres durable state, Redis coordination only, a single transactional outbox as async source of truth, W3C `traceparent` across async hops, and no legacy imports in the new `coke` package.

## Scope

In scope:

- Add backend infrastructure dependencies to `requirements.txt`.
- Add `coke` to coverage sources in `pyproject.toml`.
- Create the initial `coke` package and `coke/infra` package.
- Create `Settings.from_env()` with required `DATABASE_URL` and `REDIS_URL`, optional `APP_ENV`, and fail-closed missing-env behavior.
- Create a Flask app factory with `/healthz` and settings registration.
- Create lazy Postgres and Redis factory functions that do not connect during import or app construction.
- Create immutable `OutboxEvent` value objects for future transactional outbox rows.
- Create W3C `traceparent` helpers for outbox propagation.
- Create unit tests proving the above behavior and proving the `coke` package does not import legacy runtime modules.

Out of scope:

- Do not create schema tables or SQLAlchemy ORM models.
- Do not create Alembic config, migration environment, or revision files.
- Do not create domain modules, provider adapters, worker consumers, scheduler code, route modules beyond `/healthz`, or web code.
- Do not remove `pymongo`; legacy deletion is a later child plan.
- Do not add Mongo-backed state, compatibility shims, parser fallbacks, alias routes, or duplicate legacy implementations.

## File Structure

- Modify `requirements.txt`: add SQLAlchemy, Alembic, psycopg, and OpenTelemetry dependencies while keeping current dependencies, including `pymongo`.
- Modify `pyproject.toml`: extend coverage source to include the new `coke` package.
- Create `coke/__init__.py`: declare the clean backend package and keep imports minimal.
- Create `coke/app.py`: Flask application factory and `/healthz`; no database, Redis, worker, scheduler, or provider startup.
- Create `coke/config.py`: immutable settings and fail-closed environment parsing.
- Create `coke/infra/__init__.py`: infrastructure package marker without side effects.
- Create `coke/infra/postgres.py`: SQLAlchemy engine and session factory helpers only.
- Create `coke/infra/redis.py`: Redis client factory only.
- Create `coke/infra/outbox.py`: immutable outbox event value object.
- Create `coke/infra/tracing.py`: W3C traceparent validation, extraction, generation, and OpenTelemetry tracer access.
- Create `tests/unit/coke/test_backend_foundation.py`: focused contract tests for this foundation slice.

## Task 1: Write Backend Foundation Contract Tests

**Files:**
- Create: `tests/unit/coke/test_backend_foundation.py`

- [ ] **Step 1: Create the test directory**

Run:

```bash
mkdir -p tests/unit/coke
```

Expected: the directory `tests/unit/coke` exists.

- [ ] **Step 2: Write the failing test file**

Create `tests/unit/coke/test_backend_foundation.py` with exactly this content:

```python
from dataclasses import FrozenInstanceError
import builtins
import importlib
import re
import sys

import pytest


POSTGRES_URL = "postgresql+psycopg://coke:pass@localhost:5432/coke"
REDIS_URL = "redis://localhost:6379/0"
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_settings_from_env_reads_required_urls_and_default_app_env(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.delenv("APP_ENV", raising=False)

    settings = Settings.from_env()

    assert settings.database_url == POSTGRES_URL
    assert settings.redis_url == REDIS_URL
    assert settings.app_env == "local"


def test_settings_from_env_reads_app_env(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("APP_ENV", "test")

    settings = Settings.from_env()

    assert settings.app_env == "test"


def test_settings_from_env_fails_closed_without_database_url(monkeypatch):
    from coke.config import ConfigurationError, Settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)

    with pytest.raises(ConfigurationError, match="DATABASE_URL is required"):
        Settings.from_env()


def test_settings_from_env_fails_closed_without_redis_url(monkeypatch):
    from coke.config import ConfigurationError, Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(ConfigurationError, match="REDIS_URL is required"):
        Settings.from_env()


def test_create_app_exposes_health_and_registers_settings():
    from flask import Flask

    from coke.app import create_app
    from coke.config import Settings

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    app = create_app(settings)

    assert isinstance(app, Flask)
    assert app.config["COKE_SETTINGS"] is settings
    assert app.config["APP_ENV"] == "test"
    assert app.test_client().get("/healthz").get_json() == {"ok": True}


def test_create_app_does_not_start_network_services(monkeypatch):
    from coke.app import create_app
    from coke.config import Settings
    from coke.infra import postgres, redis

    def forbidden_postgres_call(settings):
        raise AssertionError("create_app must not create a Postgres engine")

    def forbidden_redis_call(settings):
        raise AssertionError("create_app must not create a Redis client")

    monkeypatch.setattr(postgres, "create_engine", forbidden_postgres_call)
    monkeypatch.setattr(redis, "create_redis_client", forbidden_redis_call)

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    app = create_app(settings)

    assert app.test_client().get("/healthz").status_code == 200


def test_postgres_factories_are_lazy(monkeypatch):
    from coke.config import Settings
    from coke.infra import postgres

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    calls = []
    fake_engine = object()

    def fake_create_engine(url, **kwargs):
        calls.append(("engine", url, kwargs))
        return fake_engine

    class FakeSessionFactory:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_sessionmaker(**kwargs):
        calls.append(("sessionmaker", kwargs))
        return FakeSessionFactory(**kwargs)

    monkeypatch.setattr(postgres, "sqlalchemy_create_engine", fake_create_engine)
    monkeypatch.setattr(postgres, "sessionmaker", fake_sessionmaker)

    assert calls == []
    engine = postgres.create_engine(settings)
    session_factory = postgres.create_session_factory(engine)

    assert engine is fake_engine
    assert session_factory.kwargs["bind"] is fake_engine
    assert calls[0][0] == "engine"
    assert calls[0][1] == POSTGRES_URL
    assert calls[0][2]["pool_pre_ping"] is True
    assert calls[0][2]["future"] is True
    assert calls[1][0] == "sessionmaker"


def test_redis_factory_is_lazy(monkeypatch):
    from coke.config import Settings
    from coke.infra import redis as redis_infra

    settings = Settings(database_url=POSTGRES_URL, redis_url=REDIS_URL, app_env="test")
    calls = []
    fake_client = object()

    class FakeRedis:
        @staticmethod
        def from_url(url, **kwargs):
            calls.append((url, kwargs))
            return fake_client

    monkeypatch.setattr(redis_infra.redis_lib, "Redis", FakeRedis)

    assert calls == []
    client = redis_infra.create_redis_client(settings)

    assert client is fake_client
    assert calls == [(REDIS_URL, {"decode_responses": True})]


def test_outbox_event_is_immutable_and_carries_traceparent():
    from coke.infra.outbox import OutboxEvent

    event = OutboxEvent(
        id="evt_1",
        topic="turn.inbound",
        idempotency_key="inbound:provider-message-1",
        payload={"trigger_id": "inbound:provider-message-1"},
        traceparent=TRACEPARENT,
    )

    assert event.id == "evt_1"
    assert event.topic == "turn.inbound"
    assert event.idempotency_key == "inbound:provider-message-1"
    assert event.payload["trigger_id"] == "inbound:provider-message-1"
    assert event.traceparent == TRACEPARENT
    assert event.created_at.tzinfo is not None

    with pytest.raises(FrozenInstanceError):
        event.topic = "changed"
    with pytest.raises(TypeError):
        event.payload["new"] = "value"


@pytest.mark.parametrize(
    ("field_name", "kwargs", "message"),
    [
        ("topic", {"topic": " "}, "topic must not be blank"),
        (
            "idempotency_key",
            {"idempotency_key": " "},
            "idempotency_key must not be blank",
        ),
    ],
)
def test_outbox_event_rejects_blank_required_fields(field_name, kwargs, message):
    from coke.infra.outbox import OutboxEvent

    values = {
        "id": "evt_1",
        "topic": "turn.inbound",
        "idempotency_key": "inbound:provider-message-1",
        "payload": {"trigger_id": "inbound:provider-message-1"},
        "traceparent": TRACEPARENT,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        OutboxEvent(**values)


def test_traceparent_helpers_validate_extract_and_generate():
    from coke.infra import tracing

    assert tracing.is_valid_traceparent(TRACEPARENT) is True
    assert tracing.extract_trace_id(TRACEPARENT) == "4bf92f3577b34da6a3ce929d0e0e4736"

    generated = tracing.generate_traceparent()

    assert tracing.is_valid_traceparent(generated) is True
    assert re.fullmatch(
        r"00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]",
        generated,
    )
    assert tracing.ensure_traceparent(TRACEPARENT) == TRACEPARENT
    assert tracing.is_valid_traceparent(tracing.ensure_traceparent(None)) is True

    with pytest.raises(ValueError, match="Invalid W3C traceparent"):
        tracing.extract_trace_id("not-a-traceparent")


def test_coke_package_does_not_import_legacy_runtime_modules(monkeypatch):
    imported_forbidden = []
    real_import = builtins.__import__

    def tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.partition(".")[0]
        if root in {"dao", "connector", "gateway"}:
            imported_forbidden.append(name)
            raise AssertionError(f"coke package imported legacy module {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", tracking_import)
    for module_name in list(sys.modules):
        if module_name == "coke" or module_name.startswith("coke."):
            del sys.modules[module_name]

    for module_name in (
        "coke",
        "coke.app",
        "coke.config",
        "coke.infra",
        "coke.infra.postgres",
        "coke.infra.redis",
        "coke.infra.outbox",
        "coke.infra.tracing",
    ):
        importlib.import_module(module_name)

    assert imported_forbidden == []
```

- [ ] **Step 3: Run the new tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'coke'`.

## Task 2: Add Dependencies And Coverage Source

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add backend infrastructure dependencies**

In `requirements.txt`, add these lines after `redis==5.0.4`:

```txt
SQLAlchemy>=2.0.0
alembic>=1.13.0
psycopg[binary]>=3.2.0
opentelemetry-api>=1.28.0
opentelemetry-sdk>=1.28.0
```

Keep `pymongo==4.12.0` in this task.

- [ ] **Step 2: Add `coke` to coverage sources**

In `pyproject.toml`, replace the existing coverage source line with:

```toml
source = ["agent", "dao", "util", "entity", "connector", "coke"]
```

- [ ] **Step 3: Inspect dependency and coverage diff**

Run:

```bash
git diff -- requirements.txt pyproject.toml
```

Expected: the diff adds only the five dependency lines above and adds only `"coke"` to the coverage source list.

## Task 3: Create App And Settings Foundation

**Files:**
- Create: `coke/__init__.py`
- Create: `coke/config.py`
- Create: `coke/app.py`

- [ ] **Step 1: Create the package directory**

Run:

```bash
mkdir -p coke
```

Expected: the directory `coke` exists.

- [ ] **Step 2: Create `coke/__init__.py`**

Create `coke/__init__.py` with exactly this content:

```python
"""Clean-rebuild Coke backend package."""
```

- [ ] **Step 3: Create `coke/config.py`**

Create `coke/config.py` with exactly this content:

```python
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    app_env: str = "local"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ

        database_url = (source.get("DATABASE_URL") or "").strip()
        redis_url = (source.get("REDIS_URL") or "").strip()
        app_env = (source.get("APP_ENV") or "local").strip() or "local"

        if not database_url:
            raise ConfigurationError("DATABASE_URL is required for Coke backend startup")
        if not redis_url:
            raise ConfigurationError("REDIS_URL is required for Coke backend startup")

        return cls(
            database_url=database_url,
            redis_url=redis_url,
            app_env=app_env,
        )
```

- [ ] **Step 4: Create `coke/app.py`**

Create `coke/app.py` with exactly this content:

```python
from __future__ import annotations

from flask import Flask, jsonify

from coke.config import Settings


def create_app(settings: Settings) -> Flask:
    app = Flask(__name__)
    app.config["COKE_SETTINGS"] = settings
    app.config["APP_ENV"] = settings.app_env

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app
```

- [ ] **Step 5: Run focused tests and verify remaining failures**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -v
```

Expected: some settings and app tests PASS; tests that import `coke.infra` still FAIL because infrastructure files do not exist.

## Task 4: Create Lazy Infrastructure Factories

**Files:**
- Create: `coke/infra/__init__.py`
- Create: `coke/infra/postgres.py`
- Create: `coke/infra/redis.py`

- [ ] **Step 1: Create the infrastructure package directory**

Run:

```bash
mkdir -p coke/infra
```

Expected: the directory `coke/infra` exists.

- [ ] **Step 2: Create `coke/infra/__init__.py`**

Create `coke/infra/__init__.py` with exactly this content:

```python
"""Infrastructure helpers for the clean-rebuild Coke backend."""
```

- [ ] **Step 3: Create `coke/infra/postgres.py`**

Create `coke/infra/postgres.py` with exactly this content:

```python
from __future__ import annotations

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from coke.config import Settings


def create_engine(settings: Settings) -> Engine:
    return sqlalchemy_create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
```

- [ ] **Step 4: Create `coke/infra/redis.py`**

Create `coke/infra/redis.py` with exactly this content:

```python
from __future__ import annotations

from typing import Any

import redis as redis_lib

from coke.config import Settings


def create_redis_client(settings: Settings) -> Any:
    return redis_lib.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
```

- [ ] **Step 5: Run focused tests and verify remaining failures**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -v
```

Expected: settings, app, Postgres factory, and Redis factory tests PASS; outbox and tracing tests still FAIL because `coke.infra.outbox` and `coke.infra.tracing` do not exist.

## Task 5: Create Outbox Event And Trace Helpers

**Files:**
- Create: `coke/infra/outbox.py`
- Create: `coke/infra/tracing.py`

- [ ] **Step 1: Create `coke/infra/tracing.py`**

Create `coke/infra/tracing.py` with exactly this content:

```python
from __future__ import annotations

import re
import secrets
import uuid

from opentelemetry import trace


_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-"
    r"(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<span_id>[0-9a-f]{16})-"
    r"(?P<trace_flags>[0-9a-f]{2})$"
)


def is_valid_traceparent(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    match = _TRACEPARENT_RE.fullmatch(value)
    if match is None:
        return False
    if match.group("version") == "ff":
        return False
    if match.group("trace_id") == "0" * 32:
        return False
    if match.group("span_id") == "0" * 16:
        return False
    return True


def extract_trace_id(traceparent: str) -> str:
    match = _TRACEPARENT_RE.fullmatch(traceparent)
    if match is None or not is_valid_traceparent(traceparent):
        raise ValueError("Invalid W3C traceparent")
    return match.group("trace_id")


def generate_traceparent(sampled: bool = True) -> str:
    trace_id = uuid.uuid4().hex
    span_id = secrets.token_hex(8)
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def ensure_traceparent(traceparent: str | None) -> str:
    if traceparent is None:
        return generate_traceparent()
    if not is_valid_traceparent(traceparent):
        raise ValueError("Invalid W3C traceparent")
    return traceparent


def get_tracer(name: str = "coke"):
    return trace.get_tracer(name)
```

- [ ] **Step 2: Create `coke/infra/outbox.py`**

Create `coke/infra/outbox.py` with exactly this content:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from coke.infra.tracing import is_valid_traceparent


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: str
    topic: str
    idempotency_key: str
    payload: Mapping[str, Any]
    traceparent: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self._require_nonblank("id", self.id)
        self._require_nonblank("topic", self.topic)
        self._require_nonblank("idempotency_key", self.idempotency_key)

        if not is_valid_traceparent(self.traceparent):
            raise ValueError("traceparent must be a valid W3C traceparent")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "topic", self.topic.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @staticmethod
    def _require_nonblank(field_name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be blank")
```

- [ ] **Step 3: Run focused tests and verify all pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -v
```

Expected: PASS for all tests in `tests/unit/coke/test_backend_foundation.py`.

## Task 6: Run Surface Verification And Commit

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Create: `coke/__init__.py`
- Create: `coke/app.py`
- Create: `coke/config.py`
- Create: `coke/infra/__init__.py`
- Create: `coke/infra/postgres.py`
- Create: `coke/infra/redis.py`
- Create: `coke/infra/outbox.py`
- Create: `coke/infra/tracing.py`
- Create: `tests/unit/coke/test_backend_foundation.py`

- [ ] **Step 1: Run clean backend surface verification**

Run:

```bash
zsh scripts/verify-surface clean-rebuild-backend
```

Expected: PASS and the command runs `.venv/bin/python -m pytest tests/unit/coke -v`.

- [ ] **Step 2: Run diff-aware verification suggestion**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Expected: output includes the `clean-rebuild-backend` surface because `coke/**` and `tests/unit/coke/**` changed.

- [ ] **Step 3: Run risk trigger report**

Run:

```bash
zsh scripts/review-trigger --base HEAD~1
```

Expected: command completes. Treat any output as a risk report to summarize in handoff; it is not a human-review gate.

- [ ] **Step 4: Run whitespace and conflict-marker checks**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git diff --stat
git diff -- requirements.txt pyproject.toml coke tests/unit/coke/test_backend_foundation.py
```

Expected: the diff is limited to this plan's files and contains no schema tables, migrations, domain modules, provider adapters, worker consumers, scheduler code, or web code.

- [ ] **Step 6: Commit the backend foundation slice**

Run:

```bash
git add requirements.txt pyproject.toml coke tests/unit/coke/test_backend_foundation.py
git commit -m "feat: add clean coke backend foundation"
```

Expected: a commit is created on the current branch.

## Verification Commands For This Child Plan

When implementing this child plan, run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py -v
zsh scripts/verify-surface clean-rebuild-backend
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
git diff --check
```

Expected:

- The focused pytest command passes all tests in `tests/unit/coke/test_backend_foundation.py`.
- `zsh scripts/verify-surface clean-rebuild-backend` passes and runs `.venv/bin/python -m pytest tests/unit/coke -v`.
- `zsh scripts/suggest-verification --base HEAD~1` routes the changed files to `clean-rebuild-backend`.
- `zsh scripts/review-trigger --base HEAD~1` completes and produces a non-blocking risk report.
- `git diff --check` exits 0.

## Self-Review Checklist

- [ ] Confirm the plan starts with the required `superpowers:writing-plans` header.
- [ ] Confirm the plan covers every required file and no unlisted implementation file.
- [ ] Confirm settings fail closed for missing `DATABASE_URL` and missing `REDIS_URL`.
- [ ] Confirm `APP_ENV` defaults to `local` and can be read from env.
- [ ] Confirm app construction does not create Postgres engines, Redis clients, workers, schedulers, or provider network clients.
- [ ] Confirm Postgres and Redis helpers are factories only and do not connect during import.
- [ ] Confirm `OutboxEvent` includes `id`, `topic`, `idempotency_key`, `payload`, `traceparent`, and `created_at`.
- [ ] Confirm `OutboxEvent` rejects blank `topic` and blank `idempotency_key`.
- [ ] Confirm trace helpers validate, extract, generate, and preserve W3C `traceparent`.
- [ ] Confirm `coke` imports do not touch `dao`, `connector`, or `gateway`.
- [ ] Confirm `pymongo` is not removed in this slice.
- [ ] Confirm no schema tables, Alembic revisions, domain modules, provider adapters, worker consumers, scheduler code, or web code are created.
