from __future__ import annotations

import logging
from uuid import UUID

import pytest

from coke.observability.turn_latency import turn_latency_span


def test_turn_latency_span_logs_safe_completion_fields(caplog):
    clock_values = iter([10.0, 10.125])

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        with turn_latency_span(
            "llm_json.turn_plan",
            turn_id="turn-1",
            trigger_type="InboundTurn",
            mode="interactive",
            account_id="acct-1",
            conversation_id="conv-1",
            clock=lambda: next(clock_values),
            extra={
                "model_role": "turn_plan",
                "prompt": "must-not-leak",
                "content": "must-not-leak",
            },
        ):
            pass

    record = caplog.records[-1]
    assert record.event_name == "turn_latency_event"
    assert record.getMessage().startswith("turn_latency_event {")
    assert record.phase == "llm_json.turn_plan"
    assert record.status == "ok"
    assert record.duration_ms == 125
    assert record.turn_id == "turn-1"
    assert record.model_role == "turn_plan"
    assert not hasattr(record, "prompt")
    assert not hasattr(record, "content")
    assert "must-not-leak" not in record.getMessage()


def test_turn_latency_span_logs_error_status_and_reraises(caplog):
    clock_values = iter([20.0, 20.5])

    with pytest.raises(RuntimeError):
        with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
            with turn_latency_span(
                "agent.primary",
                turn_id="turn-2",
                trigger_type="InboundTurn",
                mode="interactive",
                clock=lambda: next(clock_values),
            ):
                raise RuntimeError("boom")

    record = caplog.records[-1]
    assert record.phase == "agent.primary"
    assert record.status == "error"
    assert record.error_type == "RuntimeError"
    assert record.duration_ms == 500


def test_turn_latency_span_allows_safe_outcome_fields_from_body(caplog):
    clock_values = iter([30.0, 30.25])

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        with turn_latency_span(
            "agent.primary",
            turn_id="turn-3",
            clock=lambda: next(clock_values),
        ) as fields:
            fields["tool_count"] = 2
            fields["message_count"] = 7
            fields["content"] = "must-not-leak"

    record = caplog.records[-1]
    assert record.phase == "agent.primary"
    assert record.tool_count == 2
    assert record.message_count == 7
    assert not hasattr(record, "content")


def test_turn_latency_span_stringifies_safe_values_in_log_message(caplog):
    clock_values = iter([40.0, 40.01])
    model_id = UUID("00000000-0000-0000-0000-000000000123")

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        with turn_latency_span(
            "llm_json.turn_plan",
            clock=lambda: next(clock_values),
            extra={"model": model_id},
        ):
            pass

    record = caplog.records[-1]
    assert record.model == model_id
    assert "00000000-0000-0000-0000-000000000123" in record.getMessage()
