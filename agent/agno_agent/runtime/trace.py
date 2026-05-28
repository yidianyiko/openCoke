from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from agent.agno_agent.runtime._immutability import freeze_sequence
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.domain_results import DomainExecutionResult
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    ReminderFirePayload,
    UserTurnPayload,
)
from agent.agno_agent.runtime.result import CapabilityResult, RuntimeErrorDisposition

logger = logging.getLogger(__name__)

TraceProfile = Literal["local", "server", "eval"]
TraceContentLevel = Literal["metadata", "full"]
TraceRoute = Literal[
    "direct_reply",
    "reminder_domain",
    "scheduling_domain",
    "utility_capability",
    "reminder_fired",
    "unknown",
]
TraceOutputSource = Literal[
    "model",
    "capability_summary",
    "domain_summary",
    "empty",
]

_SCHEMA_VERSION = "agent_turn_trace.v1"
_DEFAULT_EVIDENCE_ROOT = Path("artifacts/evidence/agent-turn-traces")


@dataclass(frozen=True)
class AgentTurnTraceConfig:
    enabled: bool
    profile: TraceProfile
    content_level: TraceContentLevel


@dataclass(frozen=True)
class TraceTurn:
    input_type: Literal["user.turn", "reminder.fired"]
    message_source: str
    conversation_id: str
    owner_user_id: str
    character_id: str
    platform: str
    route_key: str | None
    occurred_at: datetime
    current_message_ids: Sequence[str]
    input_text_sha256: str | None
    input_text_chars: int
    reminder_id: str | None = None
    fire_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "current_message_ids",
            freeze_sequence(self.current_message_ids),
        )


@dataclass(frozen=True)
class TraceRuntime:
    name: Literal["agent_runtime"]
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    timeout_seconds: float | None
    failure_stage: str | None


@dataclass(frozen=True)
class TraceRouting:
    route: TraceRoute
    reason: str
    preselected_intent: str | None
    forced_args_present: bool


@dataclass(frozen=True)
class TraceAgentCall:
    agent_id: str
    role: str
    status: str
    model_role: str
    max_tokens: int | None
    tool_names: Sequence[str]
    selected_tool_names: Sequence[str]
    started_at: datetime | None
    duration_ms: int | None
    error_code: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_names", freeze_sequence(self.tool_names))
        object.__setattr__(
            self,
            "selected_tool_names",
            freeze_sequence(self.selected_tool_names),
        )


@dataclass(frozen=True)
class TraceResultRef:
    kind: Literal["domain", "capability"]
    index: int
    name: str
    outcome: str
    operation_count: int
    effect_summary: Sequence[str]
    durable_write: bool | None
    error_code: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "effect_summary",
            freeze_sequence(self.effect_summary),
        )


@dataclass(frozen=True)
class TraceGuardrail:
    name: Literal[
        "durable_write_summary",
        "unconfirmed_durable_write_promise",
        "visible_identifier_leak",
    ]
    status: Literal["passed", "failed", "skipped"]
    error_code: str | None


@dataclass(frozen=True)
class TraceOutput:
    disposition_status: str
    output_source: TraceOutputSource
    visible_message_count: int
    output_reference_count: int
    post_analyze_requested: bool


@dataclass(frozen=True)
class TraceError:
    code: str
    retryable: bool
    stage: str


@dataclass(frozen=True)
class TraceRedaction:
    content_level: TraceContentLevel
    profile: TraceProfile
    policy: Literal["allowlist"]
    hashed_ids: bool
    text_fields_present: bool


@dataclass(frozen=True)
class AgentTurnTrace:
    schema_version: Literal["agent_turn_trace.v1"]
    trace_id: str
    turn: TraceTurn
    runtime: TraceRuntime
    routing: TraceRouting
    agent_calls: Sequence[TraceAgentCall]
    result_refs: Sequence[TraceResultRef]
    guardrails: Sequence[TraceGuardrail]
    output: TraceOutput
    error: TraceError | None
    redaction: TraceRedaction

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_calls", freeze_sequence(self.agent_calls))
        object.__setattr__(self, "result_refs", freeze_sequence(self.result_refs))
        object.__setattr__(self, "guardrails", freeze_sequence(self.guardrails))


def resolve_agent_turn_trace_config() -> AgentTurnTraceConfig:
    profile = _env_literal(
        "COKE_AGENT_TURN_TRACE_PROFILE",
        {"local", "server", "eval"},
        "local",
    )
    content_default = "metadata" if profile == "server" else "full"
    content_level = _env_literal(
        "COKE_AGENT_TURN_TRACE_CONTENT",
        {"metadata", "full"},
        content_default,
    )
    if profile == "server" and content_level == "full":
        content_level = "metadata"
    enabled = _env_bool("COKE_AGENT_TURN_TRACE_ENABLED", default=True)
    return AgentTurnTraceConfig(
        enabled=enabled,
        profile=profile,  # type: ignore[arg-type]
        content_level=content_level,  # type: ignore[arg-type]
    )


def build_agent_turn_trace(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    started_at: datetime,
    finished_at: datetime | None,
    timeout_seconds: float | None,
    status: str,
    failure_stage: str | None,
    route: TraceRoute,
    reason: str,
    preselected_intent: str | None,
    forced_args_present: bool,
    tool_names: Sequence[str],
    selected_tool_names: Sequence[str],
    capability_results: Sequence[CapabilityResult],
    domain_results: Sequence[DomainExecutionResult],
    output: TraceOutput,
    error_disposition: RuntimeErrorDisposition | None,
    profile: TraceProfile | None = None,
    content_level: TraceContentLevel | None = None,
) -> AgentTurnTrace:
    config = resolve_agent_turn_trace_config()
    resolved_profile = profile or config.profile
    resolved_content_level = content_level or config.content_level
    if resolved_profile == "server" and resolved_content_level == "full":
        resolved_content_level = "metadata"
    return AgentTurnTrace(
        schema_version=_SCHEMA_VERSION,
        trace_id=f"turn-{uuid4().hex}",
        turn=_build_turn(
            agent_input=agent_input,
            run_context=run_context,
            input_message=input_message,
            profile=resolved_profile,
        ),
        runtime=TraceRuntime(
            name="agent_runtime",
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            timeout_seconds=timeout_seconds,
            failure_stage=failure_stage,
        ),
        routing=TraceRouting(
            route=route,
            reason=reason,
            preselected_intent=preselected_intent,
            forced_args_present=forced_args_present,
        ),
        agent_calls=(
            TraceAgentCall(
                agent_id="coke-interaction-agent",
                role="interaction",
                status=status,
                model_role="chat_response",
                max_tokens=2000,
                tool_names=tuple(tool_names),
                selected_tool_names=tuple(selected_tool_names),
                started_at=started_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error_code=error_disposition.code if error_disposition else None,
            ),
        ),
        result_refs=(
            *_domain_result_refs(domain_results),
            *_capability_result_refs(capability_results),
        ),
        guardrails=_guardrail_refs(error_disposition),
        output=output,
        error=_trace_error(error_disposition, failure_stage),
        redaction=TraceRedaction(
            content_level=resolved_content_level,
            profile=resolved_profile,
            policy="allowlist",
            hashed_ids=resolved_profile == "server",
            text_fields_present=False,
        ),
    )


def serialize_agent_turn_trace(trace: AgentTurnTrace) -> dict[str, Any]:
    return _jsonable(trace)


def trace_evidence_path(*, suite: str, run_id: str) -> Path:
    safe_suite = _safe_path_part(suite) or "dev"
    safe_run_id = _safe_path_part(run_id) or "run"
    return _DEFAULT_EVIDENCE_ROOT / safe_suite / f"{safe_run_id}.jsonl"


def emit_agent_turn_trace_jsonl(
    *,
    path: Path,
    trace: AgentTurnTrace,
    suite: str,
    trace_run_id: str,
    content_evidence: Mapping[str, Any] | None = None,
) -> bool:
    try:
        record: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "record_type": "agent_turn_trace",
            "recorded_at": datetime.now(UTC).isoformat(),
            "trace_run_id": trace_run_id,
            "record_id": trace.trace_id,
            "source": {
                "suite": suite,
                "profile": trace.redaction.profile,
                "runtime": trace.runtime.name,
                "worker_tag": None,
                "pid": os.getpid(),
            },
            "trace": serialize_agent_turn_trace(trace),
        }
        if (
            trace.redaction.content_level == "full"
            and trace.redaction.profile in {"local", "eval"}
            and content_evidence
        ):
            record["content_evidence"] = _jsonable(content_evidence)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except Exception:
        logger.warning(
            "trace_emit_failed trace_id=%s status=trace_emit_failed",
            trace.trace_id,
        )
        return False


def trace_summary_pointer(
    *,
    suite: str,
    run_id: str,
    record_count: int,
    enabled: bool | None = None,
    content_level: TraceContentLevel | None = None,
) -> dict[str, Any]:
    config = resolve_agent_turn_trace_config()
    return {
        "enabled": config.enabled if enabled is None else enabled,
        "schema_version": _SCHEMA_VERSION,
        "path": trace_evidence_path(suite=suite, run_id=run_id).as_posix(),
        "record_count": record_count,
        "content_level": content_level or config.content_level,
    }


def coerce_agent_turn_trace(
    value: AgentTurnTrace | Mapping[str, Any],
) -> AgentTurnTrace:
    if isinstance(value, AgentTurnTrace):
        return value
    status = str(value.get("status") or "unknown")
    now = datetime.now(UTC)
    return AgentTurnTrace(
        schema_version=_SCHEMA_VERSION,
        trace_id=f"turn-{uuid4().hex}",
        turn=TraceTurn(
            input_type="user.turn",
            message_source="legacy",
            conversation_id="unknown",
            owner_user_id="unknown",
            character_id="unknown",
            platform="unknown",
            route_key=None,
            occurred_at=now,
            current_message_ids=(),
            input_text_sha256=None,
            input_text_chars=0,
        ),
        runtime=TraceRuntime(
            name="agent_runtime",
            status=status,
            started_at=now,
            finished_at=now,
            duration_ms=0,
            timeout_seconds=None,
            failure_stage=None,
        ),
        routing=TraceRouting(
            route="unknown",
            reason=str(value.get("runtime") or "legacy_mapping"),
            preselected_intent=None,
            forced_args_present=False,
        ),
        agent_calls=(),
        result_refs=(),
        guardrails=(),
        output=TraceOutput(
            disposition_status=status or "unknown",
            output_source="empty",
            visible_message_count=0,
            output_reference_count=0,
            post_analyze_requested=False,
        ),
        error=None,
        redaction=TraceRedaction(
            content_level="metadata",
            profile="local",
            policy="allowlist",
            hashed_ids=False,
            text_fields_present=False,
        ),
    )


def _build_turn(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
    input_message: str,
    profile: TraceProfile,
) -> TraceTurn:
    reminder_id = None
    fire_id = None
    current_message_ids: Sequence[str] = ()
    if isinstance(agent_input.payload, UserTurnPayload):
        current_message_ids = agent_input.payload.current_message_ids
    elif isinstance(agent_input.payload, ReminderFirePayload):
        reminder_id = agent_input.payload.reminder_id
        fire_id = agent_input.payload.fire_id
    hash_ids = profile == "server"
    return TraceTurn(
        input_type=agent_input.input_type,
        message_source=str(
            run_context.runtime_metadata.get("message_source") or agent_input.input_type
        ),
        conversation_id=_id_value(run_context.conversation.id, hash_ids),
        owner_user_id=_id_value(run_context.user.id, hash_ids),
        character_id=_id_value(run_context.character.id, hash_ids),
        platform=run_context.platform,
        route_key=_optional_id_value(run_context.conversation.route_key, hash_ids),
        occurred_at=agent_input.occurred_at,
        current_message_ids=tuple(
            _id_value(item, hash_ids) for item in current_message_ids
        ),
        input_text_sha256=_sha256(input_message) if input_message else None,
        input_text_chars=len(input_message),
        reminder_id=_optional_id_value(reminder_id, hash_ids),
        fire_id=_optional_id_value(fire_id, hash_ids),
    )


def _domain_result_refs(
    domain_results: Sequence[DomainExecutionResult],
) -> tuple[TraceResultRef, ...]:
    refs: list[TraceResultRef] = []
    for index, result in enumerate(domain_results):
        effects = tuple(
            f"{operation.action}:{operation.effect}:{'ok' if operation.ok else 'failed'}"
            for operation in result.operations
        )
        error_code = result.error.code if result.error else None
        refs.append(
            TraceResultRef(
                kind="domain",
                index=index,
                name=result.domain,
                outcome=result.outcome,
                operation_count=len(result.operations),
                effect_summary=effects,
                durable_write=any(
                    operation.ok and operation.effect == "write"
                    for operation in result.operations
                ),
                error_code=error_code,
            )
        )
    return tuple(refs)


def _capability_result_refs(
    capability_results: Sequence[CapabilityResult],
) -> tuple[TraceResultRef, ...]:
    refs: list[TraceResultRef] = []
    for index, result in enumerate(capability_results):
        refs.append(
            TraceResultRef(
                kind="capability",
                index=index,
                name=result.name,
                outcome="ok" if result.ok else "failed",
                operation_count=1,
                effect_summary=("durable_write" if result.durable_write else "none",),
                durable_write=result.durable_write,
                error_code=result.error,
            )
        )
    return tuple(refs)


def _guardrail_refs(
    error_disposition: RuntimeErrorDisposition | None,
) -> tuple[TraceGuardrail, ...]:
    error_code = error_disposition.code if error_disposition else None
    names = (
        "durable_write_summary",
        "unconfirmed_durable_write_promise",
        "visible_identifier_leak",
    )
    guardrails: list[TraceGuardrail] = []
    for name in names:
        failed = error_code is not None and name in error_code
        guardrails.append(
            TraceGuardrail(
                name=name,  # type: ignore[arg-type]
                status="failed" if failed else "passed",
                error_code=error_code if failed else None,
            )
        )
    return tuple(guardrails)


def _trace_error(
    error_disposition: RuntimeErrorDisposition | None,
    failure_stage: str | None,
) -> TraceError | None:
    if error_disposition is None:
        return None
    return TraceError(
        code=error_disposition.code,
        retryable=error_disposition.retryable,
        stage=failure_stage or "runtime",
    )


def _duration_ms(started_at: datetime, finished_at: datetime | None) -> int | None:
    if finished_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _id_value(value: str, hash_id: bool) -> str:
    if not hash_id:
        return value
    return f"sha256:{_sha256(value)}"


def _optional_id_value(value: str | None, hash_id: bool) -> str | None:
    if value is None:
        return None
    return _id_value(value, hash_id)


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")


def _env_literal(name: str, allowed: set[str], default: str) -> str:
    value = os.environ.get(name, default).strip().lower()
    return value if value in allowed else default


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_jsonable(item) for item in sorted(value, key=str)]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
