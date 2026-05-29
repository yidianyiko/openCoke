from __future__ import annotations

import ast
import importlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    UniqueConstraint,
)
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
    schema = importlib.import_module("coke.schema")
    return schema.metadata


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


def _normalize_predicate(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "compile"):
        text = str(
            value.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
    else:
        text = str(value)
    text = text.replace('"', "")
    for table_name in sorted(EXPECTED_TABLES, key=len, reverse=True):
        text = text.replace(f"{table_name}.", "")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _type_family(column_type) -> tuple:
    if isinstance(column_type, postgresql.JSONB):
        return ("jsonb",)
    if isinstance(column_type, postgresql.UUID):
        return ("uuid",)
    if isinstance(column_type, sa.Text):
        return ("text",)
    if isinstance(column_type, sa.String):
        return ("string",)
    if isinstance(column_type, sa.BigInteger):
        return ("bigint",)
    if isinstance(column_type, sa.Integer):
        return ("integer",)
    if isinstance(column_type, sa.Boolean):
        return ("boolean",)
    if isinstance(column_type, sa.DateTime):
        return ("datetime", bool(column_type.timezone))
    return (column_type.__class__.__name__.lower(),)


def _column_inventory(table: Table) -> dict[str, dict[str, object]]:
    return {
        column.name: {
            "type": _type_family(column.type),
            "nullable": column.nullable,
            "foreign_keys": tuple(
                sorted(foreign_key.target_fullname for foreign_key in column.foreign_keys)
            ),
        }
        for column in table.columns
    }


def _constraint_inventory(table: Table) -> dict[str, object]:
    primary_key = None
    foreign_key_constraints = set()
    unique_constraints = set()
    check_constraints = set()
    for constraint in table.constraints:
        if isinstance(constraint, PrimaryKeyConstraint):
            primary_key = (
                constraint.name,
                tuple(column.name for column in constraint.columns),
            )
        elif isinstance(constraint, ForeignKeyConstraint):
            foreign_key_constraints.add(
                (
                    constraint.name,
                    tuple(column.name for column in constraint.columns),
                    tuple(element.target_fullname for element in constraint.elements),
                )
            )
        elif isinstance(constraint, UniqueConstraint):
            unique_constraints.add(
                (
                    constraint.name,
                    tuple(column.name for column in constraint.columns),
                )
            )
        elif isinstance(constraint, CheckConstraint):
            check_constraints.add(
                (
                    constraint.name,
                    _normalize_predicate(constraint.sqltext),
                )
            )
    return {
        "primary_key": primary_key,
        "foreign_key": foreign_key_constraints,
        "unique": unique_constraints,
        "check": check_constraints,
    }


def _index_inventory_from_metadata(metadata: MetaData) -> dict[str, dict[str, object]]:
    inventory = {}
    for table in metadata.tables.values():
        for index in table.indexes:
            inventory[index.name] = {
                "table_name": table.name,
                "unique": index.unique is True,
                "columns": tuple(column.name for column in index.columns),
                "postgresql_where": _normalize_predicate(
                    index.dialect_options["postgresql"]["where"]
                ),
            }
    return inventory


class RecordingOp:
    def __init__(self) -> None:
        self.metadata = MetaData()
        self.indexes: dict[str, dict[str, object]] = {}
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_tables: list[str] = []

    def create_table(self, name: str, *elements, **kwargs) -> Table:
        table = Table(name, self.metadata, *elements, **kwargs)
        return table

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        unique: bool = False,
        **kwargs,
    ) -> None:
        self.indexes[name] = {
            "table_name": table_name,
            "unique": unique is True,
            "columns": tuple(columns),
            "postgresql_where": _normalize_predicate(kwargs.get("postgresql_where")),
        }

    def drop_index(self, name: str, table_name: str | None = None, **kwargs) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_table(self, name: str, **kwargs) -> None:
        self.dropped_tables.append(name)


def _load_revision_module():
    spec = importlib.util.spec_from_file_location(
        "clean_rebuild_schema_revision_under_test",
        REVISION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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

    timed_reminder_index = _index("reminder", "uq_reminder_active_timed_duplicate")
    assert timed_reminder_index.unique is True
    assert tuple(column.name for column in timed_reminder_index.columns) == (
        "owner_account_id",
        "content_hash",
        "next_fire_at",
    )
    assert _compiled_pg_where(timed_reminder_index) == (
        "reminder.lifecycle = 'active' AND reminder.next_fire_at IS NOT NULL"
    )

    no_trigger_reminder_index = _index(
        "reminder",
        "uq_reminder_active_no_trigger_duplicate",
    )
    assert no_trigger_reminder_index.unique is True
    assert tuple(column.name for column in no_trigger_reminder_index.columns) == (
        "owner_account_id",
        "content_hash",
    )
    assert _compiled_pg_where(no_trigger_reminder_index) == (
        "reminder.lifecycle = 'active' AND reminder.next_fire_at IS NULL"
    )


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
    tree = ast.parse(source)
    imported_metadata = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "coke.schema":
            imported_metadata = any(alias.name == "metadata" for alias in node.names)

    assert imported_metadata is True
    assert "target_metadata = metadata" in source
    assert "def run_migrations_offline()" in source
    assert "literal_binds=True" in source


def test_initial_revision_has_deterministic_identity_and_no_schema_import():
    source = REVISION_PATH.read_text()
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert 'revision = "20260529_0001"' in source
    assert "down_revision = None" in source
    assert "coke" not in imported_roots
    assert ".".join(["metadata", "create_all"]) not in source
    assert ".".join(["metadata", "drop_all"]) not in source


def test_initial_revision_upgrade_matches_schema_metadata_without_live_db():
    metadata = _metadata()
    revision = _load_revision_module()
    recorder = RecordingOp()
    revision.op = recorder

    revision.upgrade()

    assert set(recorder.metadata.tables) == set(metadata.tables)
    for table_name, expected_table in metadata.tables.items():
        recorded_table = recorder.metadata.tables[table_name]
        assert _column_inventory(recorded_table) == _column_inventory(expected_table)
        recorded_constraints = _constraint_inventory(recorded_table)
        expected_constraints = _constraint_inventory(expected_table)
        assert recorded_constraints["primary_key"] == expected_constraints["primary_key"]
        assert recorded_constraints["foreign_key"] == expected_constraints["foreign_key"]
        assert recorded_constraints == expected_constraints

    assert recorder.indexes == _index_inventory_from_metadata(metadata)


def test_initial_revision_downgrade_drops_recorded_objects_in_reverse_order():
    revision = _load_revision_module()
    recorder = RecordingOp()
    revision.op = recorder

    revision.downgrade()

    assert [name for name, _table_name in recorder.dropped_indexes] == [
        "uq_reminder_active_no_trigger_duplicate",
        "uq_reminder_active_timed_duplicate",
        "uq_shared_reminder_active_duplicate",
        "uq_friendship_one_active_pair",
        "uq_channel_one_active_per_account",
    ]
    assert recorder.dropped_tables[0] == "calendar_import_item"
    assert recorder.dropped_tables[-1] == "account"
    assert set(recorder.dropped_tables) == EXPECTED_TABLES


def test_offline_sql_generation_smoke_contains_expected_objects():
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
    assert "uq_reminder_active_timed_duplicate" in result.stdout
    assert "uq_reminder_active_no_trigger_duplicate" in result.stdout
