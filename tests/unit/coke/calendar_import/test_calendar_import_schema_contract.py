from __future__ import annotations

from sqlalchemy import UniqueConstraint

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


def test_calendar_import_builds_only_on_existing_schema_tables():
    assert {"calendar_import_run", "calendar_import_item", "reminder"}.issubset(
        schema.metadata.tables
    )
    assert "google_calendar_sync_state" not in schema.metadata.tables
    assert "calendar_sync_cursor" not in schema.metadata.tables


def test_calendar_import_item_is_source_occurrence_grain():
    assert _constraint_columns(
        "calendar_import_item",
        "uq_calendar_import_item_source_occurrence",
    ) == (
        "provider_calendar_id",
        "source_event_id",
        "recurrence_instance_key",
    )
    columns = schema.metadata.tables["calendar_import_item"].columns

    assert columns["run_id"].nullable is False
    assert columns["status"].nullable is False
    assert columns["reason"].nullable is True
    assert columns["source_metadata"].nullable is False
    assert columns["reminder_id"].nullable is True


def test_calendar_import_run_stores_derived_count_columns_and_auth_handle():
    columns = schema.metadata.tables["calendar_import_run"].columns

    assert columns["account_id"].nullable is False
    assert columns["provider_type"].nullable is False
    assert columns["provider_account_id"].nullable is True
    assert columns["auth_artifact_id"].nullable is True
    assert columns["imported_count"].nullable is False
    assert columns["skipped_count"].nullable is False
    assert columns["downgraded_count"].nullable is False
    assert columns["failed_count"].nullable is False
