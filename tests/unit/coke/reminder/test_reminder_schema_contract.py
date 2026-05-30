from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from coke import schema


def _constraint_columns(table_name: str, constraint_name: str) -> tuple[str, ...]:
    table = schema.metadata.tables[table_name]
    for constraint in table.constraints:
        if (
            isinstance(constraint, UniqueConstraint)
            and constraint.name == constraint_name
        ):
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"{constraint_name} not found on {table_name}")


def _index(table_name: str, index_name: str):
    table = schema.metadata.tables[table_name]
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


def test_reminder_domain_builds_only_on_existing_schema_tables():
    assert set(
        [
            "reminder",
            "reminder_fire",
            "shared_reminder",
            "reminder_projection",
            "delivery_attempt",
            "delivery_route",
        ]
    ).issubset(schema.metadata.tables)
    assert "scheduled_actions" not in schema.metadata.tables
    assert "memo_runtime" not in schema.metadata.tables


def test_duplicate_prevention_is_schema_partial_unique_indexes():
    timed = _index("reminder", "uq_reminder_active_timed_duplicate")
    no_trigger = _index("reminder", "uq_reminder_active_no_trigger_duplicate")

    assert timed.unique is True
    assert tuple(column.name for column in timed.columns) == (
        "owner_account_id",
        "content_hash",
        "next_fire_at",
    )
    assert "lifecycle = 'active'" in _compiled_pg_where(timed)
    assert "next_fire_at IS NOT NULL" in _compiled_pg_where(timed)
    assert no_trigger.unique is True
    assert tuple(column.name for column in no_trigger.columns) == (
        "owner_account_id",
        "content_hash",
    )
    assert "lifecycle = 'active'" in _compiled_pg_where(no_trigger)
    assert "next_fire_at IS NULL" in _compiled_pg_where(no_trigger)


def test_reminder_fire_is_occurrence_grain_schema_contract():
    assert _constraint_columns("reminder_fire", "uq_reminder_fire_occurrence") == (
        "reminder_id",
        "occurrence_key",
    )
    columns = schema.metadata.tables["reminder_fire"].columns

    assert columns["fire_state"].nullable is False
    assert columns["delivery_result"].nullable is True
    assert columns["handled_at"].nullable is True
    assert columns["completed_at"].nullable is True
    assert columns["missed_catch_up"].nullable is False
