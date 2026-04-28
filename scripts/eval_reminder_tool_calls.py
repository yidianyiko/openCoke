#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_PATH = Path("scripts/reminder_test_cases.json")
DEFAULT_BASE_TIME = "2026-04-28T11:30:00+09:00"


@dataclass(frozen=True)
class ReminderEvalCase:
    input: str
    expected_intent: str
    matched_keywords: list[str]
    metadata: dict[str, Any]


@dataclass
class ReminderToolEvalResult:
    index: int
    input: str
    expected_intent: str
    passed: bool
    tool_call_count: int
    tool_calls: list[dict[str, Any]]
    error: str | None = None


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[ReminderEvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        ReminderEvalCase(
            input=str(item["input"]),
            expected_intent=str(item.get("expected_intent", "")),
            matched_keywords=list(item.get("matched_keywords") or []),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in data["test_cases"]
    ]


def select_cases(
    cases: list[ReminderEvalCase],
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[ReminderEvalCase]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    selected = cases[offset:]
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        selected = selected[:limit]
    return selected


def build_eval_input(message: str, *, current_time: str, timezone: str) -> str:
    return f"""### 当前时间
{current_time}

### 用户时区
{timezone}

### 最近对话上下文（最近5条）
（无历史消息）

### 当前用户消息
{message}"""


def _make_recorder_tool(
    recorded_calls: list[dict[str, Any]],
    *,
    stop_after_tool_call: bool,
):
    from agno.tools import tool

    @tool(
        name="visible_reminder_tool",
        stop_after_tool_call=stop_after_tool_call,
        description=(
            "Visible reminder management for deferred actions. Supports create, "
            "list, update, delete, complete, and batch for user reminders. "
            "trigger_at/new_trigger_at must be ISO 8601 with an explicit timezone "
            "offset or Z. rrule must be an RFC 5545 RRULE such as FREQ=DAILY. "
            "This eval recorder captures tool-call arguments and does not write "
            "database state."
        ),
    )
    def visible_reminder_tool_recorder(
        action: str,
        title: str | None = None,
        trigger_at: str | None = None,
        reminder_id: str | None = None,
        keyword: str | None = None,
        new_title: str | None = None,
        new_trigger_at: str | None = None,
        rrule: str | None = None,
        operations: list[dict[str, Any]] | None = None,
    ) -> str:
        call = {
            "action": action,
            "title": title,
            "trigger_at": trigger_at,
            "reminder_id": reminder_id,
            "keyword": keyword,
            "new_title": new_title,
            "new_trigger_at": new_trigger_at,
            "rrule": rrule,
            "operations": operations,
        }
        recorded_calls.append({k: v for k, v in call.items() if v is not None})
        return f"已记录提醒工具调用：{action}"

    return visible_reminder_tool_recorder


def build_reminder_tool_eval_agent(
    *,
    recorded_calls: list[dict[str, Any]],
    current_time: str,
    tool_call_limit: int,
    stop_after_tool_call: bool,
) -> Any:
    from agno.agent import Agent
    from agent.agno_agent.model_factory import create_llm_model
    from agent.prompt.agent_instructions_prompt import get_reminder_detect_instructions

    return Agent(
        id="reminder-tool-eval-agent",
        name="ReminderToolEvalAgent",
        model=create_llm_model(max_tokens=2000, role="prepare"),
        description="Evaluate whether user input should call the visible reminder tool.",
        tools=[
            _make_recorder_tool(
                recorded_calls,
                stop_after_tool_call=stop_after_tool_call,
            )
        ],
        tool_call_limit=tool_call_limit,
        instructions=get_reminder_detect_instructions(current_time),
        markdown=False,
        num_history_messages=0,
        compress_tool_results=True,
        max_tool_calls_from_history=0,
    )


def _base_timestamp(base_time: str) -> int:
    return int(datetime.fromisoformat(base_time).timestamp())


def _validate_create_like(operation: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    if not operation.get("title"):
        errors.append(f"{prefix}: create missing title")
    trigger_at = operation.get("trigger_at")
    if not trigger_at:
        errors.append(f"{prefix}: create missing trigger_at")
    else:
        try:
            parsed = datetime.fromisoformat(str(trigger_at).replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{prefix}: trigger_at is not ISO 8601")
        else:
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                errors.append(f"{prefix}: trigger_at missing timezone offset")
    rrule = operation.get("rrule")
    if rrule is not None and not str(rrule).startswith("FREQ="):
        errors.append(f"{prefix}: rrule must start with FREQ=")
    return errors


def validate_recorded_tool_calls(calls: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for call_index, call in enumerate(calls):
        action = call.get("action")
        if not action:
            errors.append(f"call {call_index}: missing action")
            continue
        if action == "create":
            errors.extend(_validate_create_like(call, f"call {call_index}"))
        if action == "update" and not (
            call.get("new_title") or call.get("new_trigger_at")
        ):
            errors.append(f"call {call_index}: update missing new_title/new_trigger_at")
        if action == "batch":
            operations = call.get("operations")
            if not isinstance(operations, list) or not operations:
                errors.append(f"call {call_index}: batch missing operations")
                continue
            for operation_index, operation in enumerate(operations):
                prefix = f"call {call_index} operation {operation_index}"
                if not isinstance(operation, dict):
                    errors.append(f"{prefix}: operation must be object")
                    continue
                operation_action = operation.get("action")
                if not operation_action:
                    errors.append(f"{prefix}: missing action")
                    continue
                if operation_action == "create":
                    errors.extend(_validate_create_like(operation, prefix))
    return errors


async def run_case(
    case: ReminderEvalCase,
    *,
    index: int,
    current_time: str,
    base_time: str,
    timezone: str,
    tool_call_limit: int,
    stop_after_tool_call: bool,
    case_timeout_seconds: float,
) -> ReminderToolEvalResult:
    recorded_calls: list[dict[str, Any]] = []
    agent = build_reminder_tool_eval_agent(
        recorded_calls=recorded_calls,
        current_time=current_time,
        tool_call_limit=tool_call_limit,
        stop_after_tool_call=stop_after_tool_call,
    )
    try:
        await asyncio.wait_for(
            agent.arun(
                input=build_eval_input(
                    case.input,
                    current_time=current_time,
                    timezone=timezone,
                ),
                session_state={
                    "user": {
                        "id": "reminder-eval-user",
                        "effective_timezone": timezone,
                    },
                    "character": {"_id": "reminder-eval-character"},
                    "conversation": {"_id": "reminder-eval-conversation"},
                    "input_timestamp": _base_timestamp(base_time),
                },
            ),
            timeout=case_timeout_seconds,
        )
        expected_tool_call = case.expected_intent == "reminder"
        validation_errors = validate_recorded_tool_calls(recorded_calls)
        passed = (
            bool(recorded_calls) and not validation_errors
            if expected_tool_call
            else not recorded_calls
        )
        return ReminderToolEvalResult(
            index=index,
            input=case.input,
            expected_intent=case.expected_intent,
            passed=passed,
            tool_call_count=len(recorded_calls),
            tool_calls=recorded_calls,
            error="; ".join(validation_errors) or None,
        )
    except Exception as exc:
        return ReminderToolEvalResult(
            index=index,
            input=case.input,
            expected_intent=case.expected_intent,
            passed=False,
            tool_call_count=len(recorded_calls),
            tool_calls=recorded_calls,
            error=f"{type(exc).__name__}: {exc}",
        )


async def run_eval(
    cases: list[ReminderEvalCase],
    *,
    offset: int,
    limit: int | None,
    current_time: str,
    base_time: str,
    timezone: str,
    tool_call_limit: int,
    stop_after_tool_call: bool,
    case_timeout_seconds: float,
) -> list[ReminderToolEvalResult]:
    selected = select_cases(cases, offset=offset, limit=limit)
    results: list[ReminderToolEvalResult] = []
    for local_index, case in enumerate(selected, start=offset):
        results.append(
            await run_case(
                case,
                index=local_index,
                current_time=current_time,
                base_time=base_time,
                timezone=timezone,
                tool_call_limit=tool_call_limit,
                stop_after_tool_call=stop_after_tool_call,
                case_timeout_seconds=case_timeout_seconds,
            )
        )
    return results


def summarize(results: list[ReminderToolEvalResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failures = [result for result in results if not result.passed]
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0,
        "failures": [asdict(result) for result in failures],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate reminder tool-calling accuracy on real user reminder inputs "
            "without ChatResponse/Interact/PostAnalyze agents."
        )
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--base-time", default=DEFAULT_BASE_TIME)
    parser.add_argument("--current-time", default="2026年04月28日11时30分")
    parser.add_argument("--tool-call-limit", type=int, default=8)
    parser.add_argument("--case-timeout-seconds", type=float, default=45)
    parser.add_argument("--no-stop-after-tool-call", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def _amain() -> int:
    args = _parse_args()
    results = await run_eval(
        load_cases(args.cases),
        offset=args.offset,
        limit=args.limit,
        current_time=args.current_time,
        base_time=args.base_time,
        timezone=args.timezone,
        tool_call_limit=args.tool_call_limit,
        stop_after_tool_call=not args.no_stop_after_tool_call,
        case_timeout_seconds=args.case_timeout_seconds,
    )
    summary = summarize(results)
    payload = {
        "cases": str(args.cases),
        "offset": args.offset,
        "limit": args.limit,
        "timezone": args.timezone,
        "base_time": args.base_time,
        "tool_call_limit": args.tool_call_limit,
        "case_timeout_seconds": args.case_timeout_seconds,
        "stop_after_tool_call": not args.no_stop_after_tool_call,
        "summary": summary,
        "results": [asdict(result) for result in results],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if summary["failed"] == 0 else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
