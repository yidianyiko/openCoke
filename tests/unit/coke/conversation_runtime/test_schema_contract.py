from __future__ import annotations

from sqlalchemy import UniqueConstraint


def _unique_columns(table, name: str) -> tuple[str, ...]:
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"{name} not found on {table.name}")


def test_conversation_runtime_schema_has_ordering_and_replay_constraints():
    from coke.schema import metadata

    conversation = metadata.tables["conversation"]
    turn = metadata.tables["turn"]
    message = metadata.tables["message"]
    output_disposition = metadata.tables["output_disposition"]
    inbound_media = metadata.tables["inbound_media"]
    outbox = metadata.tables["outbox"]

    assert "latest_inbound_seq" in conversation.c
    assert _unique_columns(conversation, "uq_conversation_account") == ("account_id",)

    assert "trigger_id" in turn.c
    assert "based_on_inbound_seq" in turn.c
    assert _unique_columns(turn, "uq_turn_trigger_id") == ("trigger_id",)

    assert "segment_index" in message.c
    assert _unique_columns(message, "uq_message_turn_segment") == (
        "turn_id",
        "segment_index",
    )

    assert "disposition" in output_disposition.c
    assert "reason_code" in output_disposition.c
    assert _unique_columns(output_disposition, "uq_output_disposition_turn") == (
        "turn_id",
    )

    assert "agent_reference" in inbound_media.c
    assert "storage_uri" in inbound_media.c

    assert "status" in outbox.c
    assert "published_at" in outbox.c
    assert "processed_at" in outbox.c
    assert "acked_at" in outbox.c
