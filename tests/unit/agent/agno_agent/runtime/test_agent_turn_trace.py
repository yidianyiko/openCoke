import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.domain_results import (
    DomainExecutionResult,
    DomainOperationResult,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.trace import (
    AgentTurnTrace,
    TraceOutput,
    build_agent_turn_trace,
    emit_agent_turn_trace_jsonl,
    resolve_agent_turn_trace_config,
    serialize_agent_turn_trace,
    trace_evidence_path,
)


def _agent_input(text: str = "secret raw input") -> AgentInput:
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv-1",
        text=text,
        payload=UserTurnPayload(current_message_ids=["msg-1"]),
        occurred_at=datetime(2026, 5, 26, 1, 0, tzinfo=UTC),
    )


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="route-1",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="raw recent history secret",
        current_time=datetime(2026, 5, 26, 1, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )


def _domain_result() -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-1",
                facts={
                    "title": "raw domain fact secret",
                    "visible_summary": "raw domain summary secret",
                },
            ),
        ),
    )


def _trace(profile: str = "server", content_level: str = "metadata") -> AgentTurnTrace:
    return build_agent_turn_trace(
        agent_input=_agent_input(),
        run_context=_run_context(),
        input_message="secret raw input",
        started_at=datetime(2026, 5, 26, 1, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 26, 1, 0, 1, tzinfo=UTC),
        timeout_seconds=None,
        status="ok",
        failure_stage=None,
        route="direct_reply",
        reason="no_tool_requested",
        preselected_intent=None,
        forced_args_present=False,
        tool_names=("reminder_domain", "timezone"),
        selected_tool_names=("timezone",),
        capability_results=(
            CapabilityResult(
                name="timezone",
                ok=True,
                content={
                    "visible_summary": "raw capability summary secret",
                    "synthesis_context": {"text": "raw synthesis secret"},
                },
            ),
        ),
        domain_results=(_domain_result(),),
        output=TraceOutput(
            disposition_status="ok",
            output_source="model",
            visible_message_count=1,
            output_reference_count=0,
            post_analyze_requested=True,
        ),
        error_disposition=None,
        profile=profile,
        content_level=content_level,
    )


def test_default_trace_config_is_local_full_and_enabled(monkeypatch):
    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_PROFILE", raising=False)
    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_ENABLED", raising=False)
    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_CONTENT", raising=False)

    config = resolve_agent_turn_trace_config()

    assert config.enabled is True
    assert config.profile == "local"
    assert config.content_level == "full"


def test_server_trace_config_defaults_to_metadata(monkeypatch):
    monkeypatch.setenv("COKE_AGENT_TURN_TRACE_PROFILE", "server")
    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_ENABLED", raising=False)
    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_CONTENT", raising=False)

    config = resolve_agent_turn_trace_config()

    assert config.enabled is True
    assert config.profile == "server"
    assert config.content_level == "metadata"


def test_metadata_trace_serialization_excludes_raw_content():
    payload = serialize_agent_turn_trace(
        _trace(profile="server", content_level="metadata")
    )
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert payload["schema_version"] == "agent_turn_trace.v1"
    assert payload["turn"]["input_text_chars"] == len("secret raw input")
    assert payload["turn"]["input_text_sha256"]
    assert "secret raw input" not in text
    assert "raw recent history secret" not in text
    assert "raw capability summary secret" not in text
    assert "raw synthesis secret" not in text
    assert "raw domain fact secret" not in text
    assert "raw domain summary secret" not in text
    assert "Traceback" not in text
    assert "user-1" not in text
    assert "char-1" not in text
    assert "conv-1" not in text
    assert "msg-1" not in text


def test_full_jsonl_evidence_can_include_explicit_content_evidence(tmp_path):
    path = tmp_path / "trace.jsonl"

    ok = emit_agent_turn_trace_jsonl(
        path=path,
        trace=_trace(profile="local", content_level="full"),
        suite="dev",
        trace_run_id="local-run",
        content_evidence={"input_text": "secret raw input"},
    )

    assert ok is True
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["trace"]["redaction"]["content_level"] == "full"
    assert record["content_evidence"]["input_text"] == "secret raw input"


def test_metadata_jsonl_evidence_omits_explicit_content_evidence(tmp_path):
    path = tmp_path / "trace.jsonl"

    ok = emit_agent_turn_trace_jsonl(
        path=path,
        trace=_trace(profile="server", content_level="metadata"),
        suite="server",
        trace_run_id="server-run",
        content_evidence={"input_text": "secret raw input"},
    )

    assert ok is True
    record = json.loads(path.read_text(encoding="utf-8"))
    assert "content_evidence" not in record
    assert "secret raw input" not in path.read_text(encoding="utf-8")


def test_trace_writer_fails_open(tmp_path, monkeypatch, caplog):
    def fail_open(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", fail_open)
    caplog.set_level(logging.WARNING)

    ok = emit_agent_turn_trace_jsonl(
        path=tmp_path / "trace.jsonl",
        trace=_trace(profile="server", content_level="metadata"),
        suite="server",
        trace_run_id="server-run",
    )

    assert ok is False
    assert "trace_emit_failed" in caplog.text
    assert "disk full" not in caplog.text


def test_trace_evidence_path_sanitizes_run_id():
    assert trace_evidence_path(
        suite="reminder-normal",
        run_id="batch/id:1",
    ).as_posix() == (
        "artifacts/evidence/agent-turn-traces/reminder-normal/batch-id-1.jsonl"
    )
