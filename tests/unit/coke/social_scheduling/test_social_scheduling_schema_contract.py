from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from coke import schema


def _unique_columns(table_name: str, constraint_name: str) -> tuple[str, ...]:
    table = schema.metadata.tables[table_name]
    for constraint in table.constraints:
        if (
            isinstance(constraint, UniqueConstraint)
            and constraint.name == constraint_name
        ):
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"{constraint_name} not found on {table_name}")


def _index(table_name: str, index_name: str):
    for index in schema.metadata.tables[table_name].indexes:
        if index.name == index_name:
            return index
    raise AssertionError(f"{index_name} not found on {table_name}")


def _compiled_where(index) -> str:
    where = index.dialect_options["postgresql"]["where"]
    assert where is not None
    return str(
        where.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_social_scheduling_tables_are_the_existing_schema_contract():
    expected_tables = {
        "friend_link",
        "friendship",
        "shared_reminder",
        "reminder_projection",
        "notification_fact",
        "notification_recipient",
    }

    assert expected_tables <= set(schema.metadata.tables)
    assert _unique_columns("friend_link", "uq_friend_link_token_hash") == (
        "token_hash",
    )
    assert _unique_columns("friend_link", "uq_friend_link_code_hash") == (
        "link_code_hash",
    )
    assert _unique_columns(
        "reminder_projection", "uq_reminder_projection_participant"
    ) == (
        "shared_reminder_id",
        "account_id",
    )
    assert _unique_columns("notification_fact", "uq_notification_fact_idempotency") == (
        "idempotency_key",
    )
    assert _unique_columns(
        "notification_recipient", "uq_notification_recipient_fact_account"
    ) == (
        "notification_fact_id",
        "recipient_account_id",
    )


def test_active_uniqueness_is_partial_and_matches_rebuild_contract():
    friendship_index = _index("friendship", "uq_friendship_one_active_pair")
    shared_index = _index("shared_reminder", "uq_shared_reminder_active_duplicate")

    assert friendship_index.unique is True
    assert tuple(column.name for column in friendship_index.columns) == (
        "account_low_id",
        "account_high_id",
    )
    assert "friendship.lifecycle = 'active'" in _compiled_where(friendship_index)

    assert shared_index.unique is True
    assert tuple(column.name for column in shared_index.columns) == (
        "creator_account_id",
        "participant_set_hash",
        "title_hash",
        "local_trigger_at",
        "captured_timezone",
        "duration_minutes",
    )
    assert "shared_reminder.status = 'active'" in _compiled_where(shared_index)


def test_notification_fact_has_no_text_or_payload_text_column():
    columns = schema.metadata.tables["notification_fact"].columns

    assert "facts" in columns
    assert "facts_hash" in columns
    assert "status" in columns
    assert "text" not in columns
    assert "payload" not in columns
    assert "payload_text" not in columns


def test_recoverable_scheduling_intent_schema_tracks_single_open_artifact():
    table = schema.metadata.tables["recoverable_scheduling_intent"]

    assert {
        "id",
        "conversation_id",
        "creator_account_id",
        "operation",
        "status",
        "blocker",
        "title",
        "local_trigger_at",
        "captured_timezone",
        "duration_minutes",
        "unresolved_reference_text",
        "source_turn_id",
        "source_input_from_seq",
        "source_input_to_seq",
        "source_message_ids",
        "facts",
        "facts_hash",
        "expires_at",
        "consumed_turn_id",
        "created_at",
        "updated_at",
    }.issubset(set(table.c.keys()))
    index = _index(
        "recoverable_scheduling_intent",
        "uq_recoverable_intent_one_open_per_conversation",
    )
    assert index.unique is True
    assert tuple(column.name for column in index.columns) == ("conversation_id",)
    assert "recoverable_scheduling_intent.status = 'open'" in _compiled_where(index)
