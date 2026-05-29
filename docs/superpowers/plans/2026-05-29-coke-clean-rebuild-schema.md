# Coke Clean Rebuild Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the first clean Postgres schema contract for the Coke rebuild, with SQLAlchemy Core metadata, Alembic bootstrap migration, and tests that pin the product invariants before domain code exists.

**Architecture:** This slice is schema-only. `coke.schema.metadata` is the single metadata source for tests and Alembic, the first Alembic revision creates the clean rebuild tables and indexes for a fresh Postgres database, and Redis remains coordination-only because durable async state is recorded in the shared Postgres `outbox` table.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x Core, Alembic, Postgres dialect features including JSONB and partial unique indexes, pytest.

---

**Plan Status:** draft
**Status Date:** 2026-05-29
**Parent Plan:** `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`, Task 3: Clean Postgres Schema And Migration Contract
**Source Specs:**
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`

**Freshness Check:** Before execution, verify this plan against current `main`, `docs/ARCHITECTURE.md`, `docs/design-docs/coke-working-contract.md`, `coke/infra/postgres.py`, `coke/infra/outbox.py`, and the source specs. The clean-rebuild contract at this point is: all durable product state in Postgres, Redis as wake/lock/pubsub only, a single transactional outbox as durable async source of truth, no Mongo-owned state, no legacy table compatibility, and no domain service implementation in this slice.

## Scope

In scope:

- Create Alembic configuration and environment for the clean rebuild schema.
- Create `coke/schema.py` with SQLAlchemy Core `Table(...)` declarations.
- Create the initial Alembic revision for a fresh clean database.
- Create unit tests that pin table presence, legacy table absence, unique constraints, partial unique indexes, key lifecycle/status/timezone/idempotency columns, migration source wiring, offline SQL generation, and import boundaries.
- Prove `outbox` is a Postgres table with durable relay and worker acknowledgement columns.

Out of scope:

- Do not implement domain services, repositories, API routes, workers, provider adapters, scheduler code, web code, or data migration code.
- Do not create compatibility tables for legacy Mongo or Gateway names.
- Do not import `dao`, `connector`, `gateway`, `pymongo`, or Mongo client code from `coke/schema.py`.
- Do not add `migrations/__init__.py` or `migrations/versions/__init__.py`; Alembic loads migration scripts by path, not by Python package import, so package marker files are not needed for this slice.

## File Structure

- Create `alembic.ini`: Alembic CLI configuration that points at `migrations`, uses `DATABASE_URL` through `migrations/env.py`, and supports offline SQL.
- Create `migrations/env.py`: Alembic environment that imports `coke.schema.metadata` as `target_metadata`, configures online migrations from `DATABASE_URL`, and configures offline SQL generation from the same URL.
- Create `migrations/versions/20260529_0001_clean_rebuild_schema.py`: deterministic initial revision with revision id `20260529_0001`, no `down_revision`, and upgrade/downgrade commands for the clean schema.
- Create `coke/schema.py`: SQLAlchemy Core metadata, table declarations, naming convention, unique constraints, partial unique indexes, and helper functions only.
- Create `tests/unit/coke/test_clean_schema_contract.py`: schema and migration contract tests.

## Execution Preflight

Run this once before Task 1 and keep `python_cmd` set in the same shell session:

```bash
python_cmd=".venv/bin/python"
if [[ ! -x "$python_cmd" ]]; then
  python_cmd="python3"
fi
```

Expected: `python_cmd` points to the repository virtualenv Python when present, otherwise to `python3`.

## Task 1: Write The Schema Contract Tests

**Files:**
- Create: `tests/unit/coke/test_clean_schema_contract.py`

- [ ] **Step 1: Create the test directory**

Run:

```bash
mkdir -p tests/unit/coke
```

Expected: the directory `tests/unit/coke` exists.

- [ ] **Step 2: Create the failing schema contract test file**

Create `tests/unit/coke/test_clean_schema_contract.py` with exactly this content:

```python
from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "coke" / "schema.py"
ENV_PATH = ROOT / "migrations" / "env.py"
REVISION_PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "20260529_0001_clean_rebuild_schema.py"
)

EXPECTED_TABLES = {
    "account",
    "agent_settings",
    "user_profile",
    "account_activation",
    "account_access",
    "credential",
    "session",
    "channel_identity",
    "auth_artifact",
    "channel",
    "delivery_route",
    "delivery_attempt",
    "conversation",
    "message",
    "inbound_media",
    "turn",
    "output_disposition",
    "outbox",
    "reminder",
    "reminder_fire",
    "friend_link",
    "friendship",
    "shared_reminder",
    "reminder_projection",
    "notification_fact",
    "notification_recipient",
    "calendar_import_run",
    "calendar_import_item",
}

LEGACY_TABLES = {
    "inputmessages",
    "outputmessages",
    "scheduled_actions",
    "friend_requests",
    "shared_reminder_requests",
}


def _metadata():
    from coke.schema import metadata

    return metadata


def _constraint_columns(table_name: str, constraint_name: str) -> tuple[str, ...]:
    table = _metadata().tables[table_name]
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == constraint_name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"{constraint_name} not found on {table_name}")


def _index(table_name: str, index_name: str):
    table = _metadata().tables[table_name]
    for index in table.indexes:
        if index.name == index_name:
            return index
    raise AssertionError(f"{index_name} not found on {table_name}")


def _compiled_pg_where(index) -> str:
    where = index.dialect_options["postgresql"]["where"]
    assert where is not None
    return str(
        where.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_metadata_contains_exact_clean_target_tables():
    metadata = _metadata()

    assert set(metadata.tables) == EXPECTED_TABLES
    assert LEGACY_TABLES.isdisjoint(metadata.tables)


def test_required_unique_constraints_are_declared():
    assert _constraint_columns(
        "channel_identity",
        "uq_channel_identity_provider_subject",
    ) == ("provider_type", "provider_subject")
    assert _constraint_columns("turn", "uq_turn_trigger_id") == ("trigger_id",)
    assert _constraint_columns("outbox", "uq_outbox_idempotency_key") == (
        "idempotency_key",
    )
    assert _constraint_columns("message", "uq_message_turn_segment") == (
        "turn_id",
        "segment_index",
    )
    assert _constraint_columns("reminder_fire", "uq_reminder_fire_occurrence") == (
        "reminder_id",
        "occurrence_key",
    )
    assert _constraint_columns(
        "calendar_import_item",
        "uq_calendar_import_item_source_occurrence",
    ) == (
        "provider_calendar_id",
        "source_event_id",
        "recurrence_instance_key",
    )


def test_required_partial_unique_indexes_are_declared_for_postgres():
    channel_index = _index("channel", "uq_channel_one_active_per_account")
    assert channel_index.unique is True
    assert tuple(column.name for column in channel_index.columns) == ("account_id",)
    assert _compiled_pg_where(channel_index) == "channel.lifecycle = 'active'"

    friendship_index = _index("friendship", "uq_friendship_one_active_pair")
    assert friendship_index.unique is True
    assert tuple(column.name for column in friendship_index.columns) == (
        "account_low_id",
        "account_high_id",
    )
    assert _compiled_pg_where(friendship_index) == "friendship.lifecycle = 'active'"

    shared_index = _index(
        "shared_reminder",
        "uq_shared_reminder_active_duplicate",
    )
    assert shared_index.unique is True
    assert tuple(column.name for column in shared_index.columns) == (
        "creator_account_id",
        "participant_set_hash",
        "title_hash",
        "local_trigger_at",
        "captured_timezone",
        "duration_minutes",
    )
    assert _compiled_pg_where(shared_index) == "shared_reminder.status = 'active'"


@pytest.mark.parametrize(
    ("table_name", "columns"),
    [
        (
            "account",
            {
                "origin",
                "default_timezone",
                "lifecycle",
                "created_at",
                "updated_at",
            },
        ),
        (
            "account_access",
            {
                "email_verification_state",
                "subscription_state",
                "suspension_state",
                "access_allowed",
                "denial_reason",
            },
        ),
        (
            "auth_artifact",
            {
                "type",
                "purpose",
                "delivery",
                "browser_session",
                "target_account_id",
                "continuation",
                "expires_at",
                "consumed_at",
                "delivery_state",
                "resend_count",
            },
        ),
        (
            "channel",
            {
                "account_id",
                "channel_identity_id",
                "provider_type",
                "lifecycle",
                "connection_state",
                "removable",
                "connected_at",
                "removed_at",
            },
        ),
        (
            "conversation",
            {"account_id", "latest_inbound_seq", "created_at", "updated_at"},
        ),
        (
            "message",
            {
                "conversation_id",
                "turn_id",
                "direction",
                "segment_index",
                "seq",
                "channel_identity_id",
                "causal_inbound_event_id",
                "text",
                "payload",
                "facts_hash",
            },
        ),
        (
            "turn",
            {
                "conversation_id",
                "trigger_id",
                "trigger_type",
                "mode",
                "based_on_inbound_seq",
                "started_at",
                "completed_at",
            },
        ),
        (
            "output_disposition",
            {"turn_id", "disposition", "reason_code", "created_at", "updated_at"},
        ),
        (
            "outbox",
            {
                "topic",
                "idempotency_key",
                "payload",
                "traceparent",
                "status",
                "published_at",
                "processed_at",
                "acked_at",
                "retry_count",
                "last_error",
            },
        ),
        (
            "reminder",
            {
                "owner_account_id",
                "content",
                "content_hash",
                "kind",
                "next_fire_at",
                "recurrence_rule",
                "captured_timezone",
                "duration_minutes",
                "lifecycle",
                "hidden_from_calendar",
                "shared_reminder_id",
            },
        ),
        (
            "reminder_fire",
            {
                "reminder_id",
                "occurrence_key",
                "due_at",
                "fire_state",
                "delivery_result",
                "handled_at",
                "completed_at",
                "missed_catch_up",
            },
        ),
        (
            "friendship",
            {
                "account_low_id",
                "account_high_id",
                "lifecycle",
                "established_at",
                "removed_at",
            },
        ),
        (
            "shared_reminder",
            {
                "creator_account_id",
                "participant_set_hash",
                "title",
                "title_hash",
                "local_trigger_at",
                "captured_timezone",
                "duration_minutes",
                "status",
                "cancelled_at",
            },
        ),
        (
            "notification_fact",
            {
                "type",
                "actor_account_id",
                "object_type",
                "object_id",
                "status",
                "facts",
                "facts_hash",
                "idempotency_key",
                "outbox_id",
            },
        ),
        (
            "notification_recipient",
            {
                "notification_fact_id",
                "recipient_account_id",
                "turn_id",
                "delivery_state",
                "error_facts",
            },
        ),
        (
            "calendar_import_run",
            {
                "account_id",
                "provider_type",
                "provider_account_id",
                "auth_artifact_id",
                "status",
                "imported_count",
                "skipped_count",
                "downgraded_count",
                "failed_count",
                "started_at",
                "completed_at",
            },
        ),
        (
            "calendar_import_item",
            {
                "run_id",
                "provider_calendar_id",
                "source_event_id",
                "recurrence_instance_key",
                "status",
                "reason",
                "source_metadata",
                "reminder_id",
            },
        ),
    ],
)
def test_key_invariant_columns_exist(table_name: str, columns: set[str]):
    table = _metadata().tables[table_name]

    assert columns.issubset(table.columns.keys())


def test_outbox_is_postgres_durable_async_source_of_truth():
    outbox = _metadata().tables["outbox"]

    assert {"processed_at", "acked_at"}.issubset(outbox.columns.keys())
    assert outbox.columns["payload"].type.__class__.__name__ == "JSONB"
    assert outbox.columns["status"].nullable is False
    assert outbox.columns["traceparent"].nullable is False
    assert outbox.columns["idempotency_key"].nullable is False


def test_schema_module_has_no_legacy_or_mongo_imports():
    tree = ast.parse(SCHEMA_PATH.read_text())
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint({"dao", "connector", "gateway", "pymongo"})
    assert "mongo" not in SCHEMA_PATH.read_text().lower()


def test_alembic_env_uses_schema_metadata_and_offline_generation():
    source = ENV_PATH.read_text()

    assert "from coke.schema import metadata" in source
    assert "target_metadata = metadata" in source
    assert "def run_migrations_offline()" in source
    assert "literal_binds=True" in source


def test_initial_revision_has_deterministic_identity_and_reverse_drop():
    source = REVISION_PATH.read_text()

    assert 'revision = "20260529_0001"' in source
    assert "down_revision = None" in source
    assert "metadata.create_all" in source
    assert "metadata.drop_all" in source


def test_offline_sql_contains_clean_tables_and_partial_unique_index():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+psycopg://coke:pass@localhost:5432/coke"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE account" in result.stdout
    assert "uq_channel_one_active_per_account" in result.stdout
    assert "WHERE lifecycle = 'active'" in result.stdout
```

- [ ] **Step 3: Run the tests and verify they fail before implementation**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/test_clean_schema_contract.py -v
```

Expected: FAIL because `coke/schema.py`, `alembic.ini`, `migrations/env.py`, and the initial migration do not exist yet.

## Task 2: Create The SQLAlchemy Core Schema Metadata

**Files:**
- Create: `coke/schema.py`
- Test: `tests/unit/coke/test_clean_schema_contract.py`

- [ ] **Step 1: Create `coke/schema.py`**

Create `coke/schema.py` with exactly this content:

```python
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _id_column() -> Column:
    return Column("id", UUID(as_uuid=False), primary_key=True)


def _created_at() -> Column:
    return Column("created_at", DateTime(timezone=True), nullable=False)


def _updated_at() -> Column:
    return Column("updated_at", DateTime(timezone=True), nullable=False)


account = Table(
    "account",
    metadata,
    _id_column(),
    Column("origin", String(32), nullable=False),
    Column("default_timezone", String(64), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    _created_at(),
    _updated_at(),
    CheckConstraint("origin in ('web_first', 'messaging_first')", name="account_origin"),
    CheckConstraint("lifecycle in ('active', 'disabled')", name="account_lifecycle"),
)

agent_settings = Table(
    "agent_settings",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("assistant_name", String(128), nullable=False),
    Column("user_address_name", String(128), nullable=True),
    Column("persona", Text(), nullable=True),
    Column("background", Text(), nullable=True),
    Column("speaking_style", Text(), nullable=True),
    Column("extra_rules", Text(), nullable=True),
    Column("proactive_enabled", Boolean(), nullable=False),
    Column("memory_enabled", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_agent_settings_account"),
)

user_profile = Table(
    "user_profile",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("real_name", String(160), nullable=True),
    Column("nickname", String(160), nullable=True),
    Column("description", Text(), nullable=True),
    Column("relationship_description", Text(), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_user_profile_account"),
)

account_activation = Table(
    "account_activation",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("first_inbound_received_at", DateTime(timezone=True), nullable=True),
    Column("activation_completed_at", DateTime(timezone=True), nullable=True),
    Column("first_guidance_sent_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_account_activation_account"),
)

account_access = Table(
    "account_access",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("email_verification_state", String(32), nullable=False),
    Column("subscription_state", String(32), nullable=False),
    Column("suspension_state", String(32), nullable=False),
    Column("access_allowed", Boolean(), nullable=False),
    Column("denial_reason", String(160), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_account_access_account"),
)

credential = Table(
    "credential",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("email", String(320), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("email_verified_at", DateTime(timezone=True), nullable=True),
    Column("reset_required", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_credential_account"),
    UniqueConstraint("email", name="uq_credential_email"),
)

session = Table(
    "session",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("token_hash", String(255), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("token_hash", name="uq_session_token_hash"),
)

channel_identity = Table(
    "channel_identity",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("provider_type", String(64), nullable=False),
    Column("provider_subject", String(255), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("is_account_anchor", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "provider_type",
        "provider_subject",
        name="uq_channel_identity_provider_subject",
    ),
)

auth_artifact = Table(
    "auth_artifact",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=True),
    Column("target_account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=True),
    Column("type", String(64), nullable=False),
    Column("purpose", String(128), nullable=False),
    Column("delivery", String(64), nullable=False),
    Column("token_hash", String(255), nullable=False),
    Column("browser_session", String(255), nullable=True),
    Column("continuation", JSONB(), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True), nullable=True),
    Column("delivery_state", String(64), nullable=False),
    Column("resend_count", Integer(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("token_hash", name="uq_auth_artifact_token_hash"),
)

channel = Table(
    "channel",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column(
        "channel_identity_id",
        UUID(as_uuid=False),
        ForeignKey("channel_identity.id"),
        nullable=False,
    ),
    Column("provider_type", String(64), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("connection_state", String(64), nullable=False),
    Column("removable", Boolean(), nullable=False),
    Column("connected_at", DateTime(timezone=True), nullable=True),
    Column("removed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
)

delivery_route = Table(
    "delivery_route",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("channel_id", UUID(as_uuid=False), ForeignKey("channel.id"), nullable=False),
    Column("provider_type", String(64), nullable=False),
    Column("provider_address", String(255), nullable=False),
    Column("route_key", String(255), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("route_key", name="uq_delivery_route_route_key"),
)

conversation = Table(
    "conversation",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("latest_inbound_seq", BigInteger(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_conversation_account"),
)

turn = Table(
    "turn",
    metadata,
    _id_column(),
    Column("conversation_id", UUID(as_uuid=False), ForeignKey("conversation.id"), nullable=False),
    Column("trigger_id", String(255), nullable=False),
    Column("trigger_type", String(64), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("based_on_inbound_seq", BigInteger(), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("trigger_id", name="uq_turn_trigger_id"),
)

message = Table(
    "message",
    metadata,
    _id_column(),
    Column("conversation_id", UUID(as_uuid=False), ForeignKey("conversation.id"), nullable=False),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=True),
    Column("direction", String(32), nullable=False),
    Column("segment_index", Integer(), nullable=True),
    Column("seq", BigInteger(), nullable=True),
    Column(
        "channel_identity_id",
        UUID(as_uuid=False),
        ForeignKey("channel_identity.id"),
        nullable=True,
    ),
    Column("causal_inbound_event_id", String(255), nullable=True),
    Column("text", Text(), nullable=True),
    Column("payload", JSONB(), nullable=False),
    Column("facts_hash", String(128), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("turn_id", "segment_index", name="uq_message_turn_segment"),
)

inbound_media = Table(
    "inbound_media",
    metadata,
    _id_column(),
    Column("message_id", UUID(as_uuid=False), ForeignKey("message.id"), nullable=False),
    Column("media_type", String(64), nullable=False),
    Column("storage_uri", Text(), nullable=False),
    Column("processing_status", String(64), nullable=False),
    Column("agent_reference", JSONB(), nullable=False),
    _created_at(),
    _updated_at(),
)

output_disposition = Table(
    "output_disposition",
    metadata,
    _id_column(),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=False),
    Column("disposition", String(64), nullable=False),
    Column("reason_code", String(160), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("turn_id", name="uq_output_disposition_turn"),
)

outbox = Table(
    "outbox",
    metadata,
    _id_column(),
    Column("topic", String(128), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("traceparent", String(55), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("processed_at", DateTime(timezone=True), nullable=True),
    Column("acked_at", DateTime(timezone=True), nullable=True),
    Column("retry_count", Integer(), nullable=False),
    Column("last_error", Text(), nullable=True),
    UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
)

delivery_attempt = Table(
    "delivery_attempt",
    metadata,
    _id_column(),
    Column("route_id", UUID(as_uuid=False), ForeignKey("delivery_route.id"), nullable=False),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=True),
    Column("message_id", UUID(as_uuid=False), ForeignKey("message.id"), nullable=True),
    Column("provider_type", String(64), nullable=False),
    Column("provider_message_id", String(255), nullable=True),
    Column("provider_idempotency_key", String(255), nullable=False),
    Column("status", String(32), nullable=False),
    Column("error_code", String(160), nullable=True),
    Column("attempted_at", DateTime(timezone=True), nullable=False),
    Column("delivered_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "provider_type",
        "provider_idempotency_key",
        name="uq_delivery_attempt_provider_idempotency",
    ),
)

reminder = Table(
    "reminder",
    metadata,
    _id_column(),
    Column("owner_account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("content", Text(), nullable=False),
    Column("content_hash", String(128), nullable=False),
    Column("kind", String(64), nullable=False),
    Column("next_fire_at", DateTime(timezone=True), nullable=True),
    Column("recurrence_rule", JSONB(), nullable=False),
    Column("captured_timezone", String(64), nullable=False),
    Column("duration_minutes", Integer(), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("hidden_from_calendar", Boolean(), nullable=False),
    Column(
        "shared_reminder_id",
        UUID(as_uuid=False),
        ForeignKey("shared_reminder.id"),
        nullable=True,
    ),
    _created_at(),
    _updated_at(),
)

reminder_fire = Table(
    "reminder_fire",
    metadata,
    _id_column(),
    Column("reminder_id", UUID(as_uuid=False), ForeignKey("reminder.id"), nullable=False),
    Column("occurrence_key", String(255), nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=False),
    Column("fire_state", String(64), nullable=False),
    Column("delivery_result", String(64), nullable=True),
    Column("handled_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("missed_catch_up", Boolean(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "reminder_id",
        "occurrence_key",
        name="uq_reminder_fire_occurrence",
    ),
)

friend_link = Table(
    "friend_link",
    metadata,
    _id_column(),
    Column("owner_account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("token_hash", String(255), nullable=False),
    Column("link_code_hash", String(255), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("reset_at", DateTime(timezone=True), nullable=True),
    Column("disabled_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("token_hash", name="uq_friend_link_token_hash"),
    UniqueConstraint("link_code_hash", name="uq_friend_link_code_hash"),
)

friendship = Table(
    "friendship",
    metadata,
    _id_column(),
    Column("account_low_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("account_high_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("established_at", DateTime(timezone=True), nullable=False),
    Column("removed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    CheckConstraint("account_low_id <> account_high_id", name="friendship_not_self"),
)

shared_reminder = Table(
    "shared_reminder",
    metadata,
    _id_column(),
    Column("creator_account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("participant_set_hash", String(128), nullable=False),
    Column("title", Text(), nullable=False),
    Column("title_hash", String(128), nullable=False),
    Column("local_trigger_at", DateTime(timezone=False), nullable=False),
    Column("captured_timezone", String(64), nullable=False),
    Column("duration_minutes", Integer(), nullable=False),
    Column("status", String(32), nullable=False),
    Column("cancelled_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
)

reminder_projection = Table(
    "reminder_projection",
    metadata,
    _id_column(),
    Column(
        "shared_reminder_id",
        UUID(as_uuid=False),
        ForeignKey("shared_reminder.id"),
        nullable=False,
    ),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("reminder_id", UUID(as_uuid=False), ForeignKey("reminder.id"), nullable=False),
    Column("lifecycle", String(32), nullable=False),
    Column("completion_status", String(64), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "shared_reminder_id",
        "account_id",
        name="uq_reminder_projection_participant",
    ),
)

notification_fact = Table(
    "notification_fact",
    metadata,
    _id_column(),
    Column("type", String(64), nullable=False),
    Column("actor_account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=True),
    Column("object_type", String(64), nullable=False),
    Column("object_id", UUID(as_uuid=False), nullable=False),
    Column("status", String(64), nullable=False),
    Column("facts", JSONB(), nullable=False),
    Column("facts_hash", String(128), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("outbox_id", UUID(as_uuid=False), ForeignKey("outbox.id"), nullable=False),
    _created_at(),
    UniqueConstraint("idempotency_key", name="uq_notification_fact_idempotency"),
)

notification_recipient = Table(
    "notification_recipient",
    metadata,
    _id_column(),
    Column(
        "notification_fact_id",
        UUID(as_uuid=False),
        ForeignKey("notification_fact.id"),
        nullable=False,
    ),
    Column("recipient_account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=True),
    Column("delivery_state", String(64), nullable=False),
    Column("error_facts", JSONB(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint(
        "notification_fact_id",
        "recipient_account_id",
        name="uq_notification_recipient_fact_account",
    ),
)

calendar_import_run = Table(
    "calendar_import_run",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("provider_type", String(64), nullable=False),
    Column("provider_account_id", String(255), nullable=True),
    Column("auth_artifact_id", UUID(as_uuid=False), ForeignKey("auth_artifact.id"), nullable=True),
    Column("status", String(64), nullable=False),
    Column("imported_count", Integer(), nullable=False),
    Column("skipped_count", Integer(), nullable=False),
    Column("downgraded_count", Integer(), nullable=False),
    Column("failed_count", Integer(), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
)

calendar_import_item = Table(
    "calendar_import_item",
    metadata,
    _id_column(),
    Column("run_id", UUID(as_uuid=False), ForeignKey("calendar_import_run.id"), nullable=False),
    Column("provider_calendar_id", String(255), nullable=False),
    Column("source_event_id", String(255), nullable=False),
    Column("recurrence_instance_key", String(255), nullable=False),
    Column("status", String(64), nullable=False),
    Column("reason", Text(), nullable=True),
    Column("source_metadata", JSONB(), nullable=False),
    Column("reminder_id", UUID(as_uuid=False), ForeignKey("reminder.id"), nullable=True),
    _created_at(),
    UniqueConstraint(
        "provider_calendar_id",
        "source_event_id",
        "recurrence_instance_key",
        name="uq_calendar_import_item_source_occurrence",
    ),
)

Index(
    "uq_channel_one_active_per_account",
    channel.c.account_id,
    unique=True,
    postgresql_where=channel.c.lifecycle == "active",
)
Index(
    "uq_friendship_one_active_pair",
    friendship.c.account_low_id,
    friendship.c.account_high_id,
    unique=True,
    postgresql_where=friendship.c.lifecycle == "active",
)
Index(
    "uq_shared_reminder_active_duplicate",
    shared_reminder.c.creator_account_id,
    shared_reminder.c.participant_set_hash,
    shared_reminder.c.title_hash,
    shared_reminder.c.local_trigger_at,
    shared_reminder.c.captured_timezone,
    shared_reminder.c.duration_minutes,
    unique=True,
    postgresql_where=shared_reminder.c.status == "active",
)
```

- [ ] **Step 2: Run the schema-only tests and verify expected remaining failures**

Run:

```bash
$python_cmd -m pytest \
  tests/unit/coke/test_clean_schema_contract.py::test_metadata_contains_exact_clean_target_tables \
  tests/unit/coke/test_clean_schema_contract.py::test_required_unique_constraints_are_declared \
  tests/unit/coke/test_clean_schema_contract.py::test_required_partial_unique_indexes_are_declared_for_postgres \
  tests/unit/coke/test_clean_schema_contract.py::test_key_invariant_columns_exist \
  tests/unit/coke/test_clean_schema_contract.py::test_outbox_is_postgres_durable_async_source_of_truth \
  tests/unit/coke/test_clean_schema_contract.py::test_schema_module_has_no_legacy_or_mongo_imports \
  -v
```

Expected: PASS for these schema metadata tests. Alembic-related tests still fail until Task 3.

## Task 3: Add Alembic Configuration And Initial Revision

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/20260529_0001_clean_rebuild_schema.py`
- Test: `tests/unit/coke/test_clean_schema_contract.py`

- [ ] **Step 1: Create the migration directory**

Run:

```bash
mkdir -p migrations/versions
```

Expected: `migrations/versions` exists. Do not add package marker files unless a later import-based tool requires them.

- [ ] **Step 2: Create `alembic.ini`**

Create `alembic.ini` with exactly this content:

```ini
[alembic]
script_location = migrations
prepend_sys_path = .
path_separator = os
sqlalchemy.url = postgresql+psycopg://coke:pass@localhost:5432/coke

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Create `migrations/env.py`**

Create `migrations/env.py` with exactly this content:

```python
from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from coke.schema import metadata


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        config.get_main_option("sqlalchemy.url"),
    )


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create the deterministic initial revision**

Create `migrations/versions/20260529_0001_clean_rebuild_schema.py` with exactly this content:

```python
from __future__ import annotations

from alembic import op

from coke.schema import metadata


revision = "20260529_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata.create_all(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    metadata.drop_all(bind=bind, checkfirst=False)
```

This initial revision is for a fresh clean-rebuild database only. Future schema edits must add new revision files instead of changing this revision after it has been executed outside a disposable development database.

- [ ] **Step 5: Run the full schema contract test file**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/test_clean_schema_contract.py -v
```

Expected: PASS. The offline SQL test must show Alembic can emit SQL without a live database.

- [ ] **Step 6: Verify offline SQL manually**

Run:

```bash
DATABASE_URL="postgresql+psycopg://coke:pass@localhost:5432/coke" \
  $python_cmd -m alembic upgrade head --sql > /tmp/coke-clean-schema.sql
rg -n "CREATE TABLE account|uq_channel_one_active_per_account|WHERE lifecycle = 'active'" /tmp/coke-clean-schema.sql
```

Expected: the `rg` command prints lines for `CREATE TABLE account`, the partial unique index name `uq_channel_one_active_per_account`, and `WHERE lifecycle = 'active'`.

## Task 4: Run Slice Verification And Commit

**Files:**
- Verify: `alembic.ini`
- Verify: `migrations/env.py`
- Verify: `migrations/versions/20260529_0001_clean_rebuild_schema.py`
- Verify: `coke/schema.py`
- Verify: `tests/unit/coke/test_clean_schema_contract.py`

- [ ] **Step 1: Run backend surface verification**

Run:

```bash
zsh scripts/verify-surface clean-rebuild-backend
```

Expected: PASS. This runs the unit tests under `tests/unit/coke -v` through the repository Python resolver.

- [ ] **Step 2: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: `suggest-verification` includes `clean-rebuild-backend` or a broader backend/repo surface. `review-trigger` may report risk because this is an initial schema and migration contract; record the report in the handoff, but it does not block commit by itself.

- [ ] **Step 3: Run repository structure checks**

Run:

```bash
zsh scripts/check
git diff --check
```

Expected: PASS with no whitespace errors.

- [ ] **Step 4: Commit the schema slice**

Run:

```bash
git status --short
git add alembic.ini migrations/env.py migrations/versions/20260529_0001_clean_rebuild_schema.py coke/schema.py tests/unit/coke/test_clean_schema_contract.py
git commit -m "feat: add clean rebuild schema"
```

Expected: one commit containing only the schema, Alembic, and schema contract test files for this slice.

## Self-Review Checklist

Before handing off the executed schema slice, verify each item explicitly:

- [ ] The metadata table set is exactly the clean target table set from the parent plan and specs.
- [ ] Legacy table names `inputmessages`, `outputmessages`, `scheduled_actions`, `friend_requests`, and `shared_reminder_requests` are absent.
- [ ] The partial unique indexes for active channel, active friendship pair, and active shared-reminder duplicate are present and compile for the Postgres dialect.
- [ ] Unique constraints for `channel_identity`, `turn.trigger_id`, `outbox.idempotency_key`, `message(turn_id, segment_index)`, `reminder_fire(reminder_id, occurrence_key)`, and `calendar_import_item(provider_calendar_id, source_event_id, recurrence_instance_key)` are present.
- [ ] Lifecycle, status, timezone, idempotency, and delivery acknowledgement columns named in the specs are present.
- [ ] The `outbox` table has durable Postgres relay and worker acknowledgement state through `published_at`, `processed_at`, `acked_at`, `status`, `retry_count`, and `last_error`.
- [ ] `migrations/env.py` imports `coke.schema.metadata` as `target_metadata` and can emit offline SQL without connecting to Postgres.
- [ ] The initial revision has `revision = "20260529_0001"` and `down_revision = None`.
- [ ] `coke/schema.py` imports only SQLAlchemy modules and does not import legacy runtime modules or Mongo libraries.
- [ ] Verification commands passed, and the commit contains no domain services, repositories, routes, workers, provider adapters, scheduler code, web code, or compatibility code.
