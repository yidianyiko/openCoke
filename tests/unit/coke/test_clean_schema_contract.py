from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

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
    ROOT / "migrations" / "versions" / "20260529_0001_clean_rebuild_schema.py"
)
PRE_REPLY_INPUT_WINDOW_REVISION_PATH = (
    ROOT / "migrations" / "versions" / "20260531_0001_pre_reply_input_windows.py"
)
RECOVERABLE_INTENT_REVISION_PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "20260607_0001_recoverable_scheduling_intent.py"
)
HEAD_REVISION_PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "20260607_0002_delivery_attempt_diagnostics.py"
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
    "staged_command",
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
    "recoverable_scheduling_intent",
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
        if (
            isinstance(constraint, UniqueConstraint)
            and constraint.name == constraint_name
        ):
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
        return ("string", column_type.length)
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
                sorted(
                    foreign_key.target_fullname for foreign_key in column.foreign_keys
                )
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

    def add_column(self, table_name: str, column: sa.Column, **kwargs) -> None:
        self.metadata.tables[table_name].append_column(column)

    def drop_column(self, table_name: str, column_name: str, **kwargs) -> None:
        table = self.metadata.tables[table_name]
        table._columns.remove(table.c[column_name])

    def alter_column(self, table_name: str, column_name: str, **kwargs) -> None:
        column = self.metadata.tables[table_name].c[column_name]
        if "server_default" in kwargs:
            column.server_default = kwargs["server_default"]

    def create_check_constraint(
        self,
        name: str,
        table_name: str,
        condition: str,
        **kwargs,
    ) -> None:
        self.metadata.tables[table_name].append_constraint(
            CheckConstraint(condition, name=name)
        )

    def create_unique_constraint(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        **kwargs,
    ) -> None:
        table = self.metadata.tables[table_name]
        table.append_constraint(
            UniqueConstraint(*(table.c[column] for column in columns), name=name)
        )

    def drop_constraint(
        self,
        name: str,
        table_name: str,
        type_: str | None = None,
        **kwargs,
    ) -> None:
        table = self.metadata.tables[table_name]
        for constraint in list(table.constraints):
            if constraint.name == name:
                table.constraints.remove(constraint)
                return

    def execute(self, statement) -> None:
        return None

    def f(self, name: str) -> str:
        return name


def _offline_sql() -> str:
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
    return result.stdout


def _load_revision_module(
    revision_path: Path = REVISION_PATH,
    module_name: str = "clean_rebuild_schema_revision_under_test",
):
    spec = importlib.util.spec_from_file_location(
        module_name,
        revision_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_migration_chain():
    revision_paths = (
        REVISION_PATH,
        PRE_REPLY_INPUT_WINDOW_REVISION_PATH,
        RECOVERABLE_INTENT_REVISION_PATH,
        HEAD_REVISION_PATH,
    )
    return tuple(
        _load_revision_module(
            revision_path,
            f"clean_rebuild_schema_revision_{index}_under_test",
        )
        for index, revision_path in enumerate(revision_paths)
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
    assert _constraint_columns("message", "uq_message_inbound_seq") == (
        "conversation_id",
        "direction",
        "seq",
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
            {
                "account_id",
                "latest_inbound_seq",
                "last_closed_inbound_seq",
                "created_at",
                "updated_at",
            },
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
                "input_from_seq",
                "input_to_seq",
                "superseded_by_inbound_seq",
                "started_at",
                "completed_at",
            },
        ),
        (
            "staged_command",
            {
                "turn_id",
                "domain",
                "operation",
                "idempotency_key",
                "command_payload",
                "preview_facts",
                "status",
                "materialized_at",
                "created_at",
                "updated_at",
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
    assert "def _database_url(" in source
    assert "require_env=True" in source
    assert "DATABASE_URL is required for online migrations" in source


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


def test_pre_reply_input_window_revision_has_expected_identity():
    source = PRE_REPLY_INPUT_WINDOW_REVISION_PATH.read_text()
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert 'revision = "20260531_0001"' in source
    assert 'down_revision = "20260529_0001"' in source
    assert "coke" not in imported_roots
    assert ".".join(["metadata", "create_all"]) not in source
    assert ".".join(["metadata", "drop_all"]) not in source


def test_recoverable_scheduling_intent_revision_has_expected_identity():
    source = RECOVERABLE_INTENT_REVISION_PATH.read_text()
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert 'revision = "20260607_0001"' in source
    assert 'down_revision = "20260531_0001"' in source
    assert "coke" not in imported_roots
    assert ".".join(["metadata", "create_all"]) not in source
    assert ".".join(["metadata", "drop_all"]) not in source


def test_delivery_attempt_diagnostics_revision_has_expected_identity():
    source = HEAD_REVISION_PATH.read_text()
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert 'revision = "20260607_0002"' in source
    assert 'down_revision = "20260607_0001"' in source
    assert "coke" not in imported_roots
    assert ".".join(["metadata", "create_all"]) not in source
    assert ".".join(["metadata", "drop_all"]) not in source


def test_migration_chain_upgrade_matches_schema_metadata_without_live_db():
    metadata = _metadata()
    revisions = _load_migration_chain()
    recorder = RecordingOp()
    for revision in revisions:
        revision.op = recorder

    for revision in revisions:
        revision.upgrade()

    assert set(recorder.metadata.tables) == set(metadata.tables)
    for table_name, expected_table in metadata.tables.items():
        recorded_table = recorder.metadata.tables[table_name]
        assert _column_inventory(recorded_table) == _column_inventory(expected_table)
        recorded_constraints = _constraint_inventory(recorded_table)
        expected_constraints = _constraint_inventory(expected_table)
        assert (
            recorded_constraints["primary_key"] == expected_constraints["primary_key"]
        )
        assert (
            recorded_constraints["foreign_key"] == expected_constraints["foreign_key"]
        )
        assert recorded_constraints == expected_constraints

    assert recorder.indexes == _index_inventory_from_metadata(metadata)


def test_migration_chain_downgrade_drops_recorded_objects_in_reverse_order():
    revisions = _load_migration_chain()
    recorder = RecordingOp()
    for revision in revisions:
        revision.op = recorder

    for revision in revisions:
        revision.upgrade()
    for revision in reversed(revisions):
        revision.downgrade()

    assert [name for name, _table_name in recorder.dropped_indexes] == [
        "uq_recoverable_intent_one_open_per_conversation",
        "uq_reminder_active_no_trigger_duplicate",
        "uq_reminder_active_timed_duplicate",
        "uq_shared_reminder_active_duplicate",
        "uq_friendship_one_active_pair",
        "uq_channel_one_active_per_account",
    ]
    assert recorder.dropped_tables[0] == "recoverable_scheduling_intent"
    assert recorder.dropped_tables[1] == "staged_command"
    assert recorder.dropped_tables[-1] == "account"
    assert set(recorder.dropped_tables) == EXPECTED_TABLES

    drop_position = {
        table_name: position
        for position, table_name in enumerate(recorder.dropped_tables)
    }
    for child_table in recorder.metadata.tables.values():
        for constraint in child_table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            for element in constraint.elements:
                parent_name = element.column.table.name
                assert (
                    drop_position[child_table.name] < drop_position[parent_name]
                ), f"{child_table.name} must be dropped before {parent_name}"


def test_offline_sql_generation_smoke_contains_expected_objects():
    sql = _offline_sql()

    assert "CREATE TABLE account" in sql
    assert "uq_channel_one_active_per_account" in sql
    assert "uq_reminder_active_timed_duplicate" in sql
    assert "uq_reminder_active_no_trigger_duplicate" in sql


def test_offline_sql_uses_exact_schema_constraint_names_once():
    sql = _offline_sql()

    assert "CONSTRAINT ck_account_account_origin " in sql
    assert "CONSTRAINT ck_account_account_lifecycle " in sql
    assert "CONSTRAINT ck_friendship_friendship_not_self " in sql
    assert "ck_account_ck_" not in sql
    assert "ck_friendship_ck_" not in sql
    assert "CONSTRAINT fk_notification_recipient_fact " in sql
    assert "CONSTRAINT pk_account PRIMARY KEY (id)" in sql
    assert "CONSTRAINT uq_channel_identity_provider_subject UNIQUE" in sql


def test_offline_sql_preserves_key_type_details():
    sql = _offline_sql()

    assert "origin VARCHAR(32) NOT NULL" in sql
    assert "default_timezone VARCHAR(64) NOT NULL" in sql
    assert "provider_subject VARCHAR(255) NOT NULL" in sql
    assert "payload JSONB NOT NULL" in sql
    assert "local_trigger_at TIMESTAMP WITHOUT TIME ZONE NOT NULL" in sql
    assert "next_fire_at TIMESTAMP WITH TIME ZONE" in sql
