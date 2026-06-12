#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SENSIBLE_CATEGORIES = frozenset(
    {"done", "needs_choice", "needs_input", "needs_confirmation"}
)


@dataclass(frozen=True, slots=True)
class ProbeCase:
    name: str
    message: str
    expect_domain: str | None
    expect_op: str | None
    expect_categories: tuple[str, ...] = ()
    allowed_not_possible_statuses: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProbeResult:
    case: ProbeCase
    plan_actions: tuple[tuple[str, str], ...] = ()
    plan_payload: Any = None
    compiled_ok: bool = False
    compiled_payload: Any = None
    outcome_category: str | None = None
    outcome_status: str | None = None
    outcome_payload: Any = None
    segments: tuple[str, ...] = ()
    state_change_calls: int = 0
    exception: str | None = None
    passed: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RawPathResult:
    plan: Any
    compiled: Any
    settled_outcome: Any
    segments: tuple[str, ...]
    state_change_calls: int


class RecordingGuard:
    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        self.state_change_calls = 0

    def guard_state_change(self, turn_id: str | None = None) -> None:
        self.state_change_calls += 1


REQUIRED_CORPUS: tuple[ProbeCase, ...] = (
    ProbeCase(
        "reminder_create_timed",
        "提醒我明天9点跑步",
        "reminder",
        "create",
        ("done", "needs_input", "needs_confirmation"),
    ),
    ProbeCase(
        "reminder_create_vague",
        "提醒我待会跑步",
        "reminder",
        "create",
        ("done", "needs_input", "needs_confirmation"),
    ),
    ProbeCase(
        "reminder_create_recurring",
        "每周一9点提醒我开会",
        "reminder",
        "create",
        ("done", "needs_input", "needs_confirmation"),
    ),
    ProbeCase(
        "reminder_create_no_trigger",
        "提醒我买牛奶",
        "reminder",
        "create",
        ("needs_input", "done"),
    ),
    ProbeCase(
        "reminder_batch_create",
        "提醒我买牛奶也提醒我打电话",
        "reminder",
        "batch_create",
        ("done", "needs_input"),
    ),
    ProbeCase("reminder_list_all", "我有哪些提醒", "reminder", "list", ("done",)),
    ProbeCase(
        "reminder_list_friday", "我周五有什么提醒", "reminder", "list", ("done",)
    ),
    ProbeCase(
        "reminder_update",
        "把跑步提醒改到晚上8点",
        "reminder",
        "update",
        ("done", "needs_choice", "needs_input", "needs_confirmation"),
    ),
    ProbeCase(
        "reminder_delete",
        "删掉跑步提醒",
        "reminder",
        "delete",
        ("done", "needs_choice", "needs_input"),
    ),
    ProbeCase(
        "reminder_complete",
        "完成跑步提醒",
        "reminder",
        "complete",
        ("done", "needs_choice", "needs_input"),
    ),
    ProbeCase(
        "shared_create",
        "和老王明天9点开会",
        "social_scheduling",
        "create_shared_reminder",
        ("done", "needs_choice", "needs_input", "needs_confirmation"),
        ("inactive_receiver", "not_found", "unreachable"),
    ),
    ProbeCase(
        "shared_list",
        "我有哪些共享提醒",
        "social_scheduling",
        "list_shared",
        ("done", "needs_choice", "needs_input"),
    ),
    ProbeCase(
        "shared_cancel",
        "取消和老王的会议",
        "social_scheduling",
        "cancel_shared_reminder",
        ("done", "needs_choice", "needs_input"),
        ("inactive_receiver", "not_found", "unreachable"),
    ),
    ProbeCase(
        "friend_link",
        "给我一个加好友链接",
        "friendship",
        "get_friend_link",
        ("done", "needs_input"),
        ("unreachable",),
    ),
    ProbeCase("friend_list", "我有哪些好友", "friendship", "list_friends", ("done",)),
    ProbeCase(
        "settings_timezone", "把时区改成东京", "settings", "set_timezone", ("done",)
    ),
    ProbeCase("converse", "在吗最近怎么样", None, None, ()),
    ProbeCase(
        "ambiguous_delete",
        "删掉提醒",
        "reminder",
        "delete",
        ("needs_choice", "needs_input", "done"),
    ),
)


EXTENDED_CORPUS: tuple[ProbeCase, ...] = (
    ProbeCase(
        "shared_availability",
        "老王明天下午有空吗",
        "social_scheduling",
        "availability_query",
        ("done", "needs_choice", "needs_input"),
        ("inactive_receiver", "not_found", "unreachable"),
    ),
    ProbeCase(
        "friend_add_code",
        "用好友码 ABC123 加好友",
        "friendship",
        "add_via_code",
        ("done", "needs_input"),
        ("invalid_code", "used_code", "unreachable"),
    ),
    ProbeCase(
        "friend_remove",
        "移除老王这个好友",
        "friendship",
        "remove_friend",
        ("done", "needs_choice", "needs_input"),
        ("not_found", "unreachable"),
    ),
    ProbeCase(
        "settings_toggle_proactive",
        "关闭主动提醒",
        "settings",
        "toggle_proactive",
        ("done",),
    ),
    ProbeCase(
        "settings_toggle_memory",
        "不要记住这些偏好",
        "settings",
        "toggle_memory",
        ("done",),
    ),
    ProbeCase(
        "settings_update", "以后回复简短一点", "settings", "update_settings", ("done",)
    ),
    ProbeCase(
        "calendar_import",
        "导入我的谷歌日历",
        "calendar_import",
        "import",
        ("needs_input", "done"),
    ),
)


SETUP_CASES: tuple[ProbeCase, ...] = (
    ProbeCase(
        "setup_run_reminder", "提醒我明天7点跑步", "reminder", "create", ("done",)
    ),
    ProbeCase(
        "setup_water_reminder", "提醒我明天10点喝水", "reminder", "create", ("done",)
    ),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    cases = REQUIRED_CORPUS + (() if args.required_only else EXTENDED_CORPUS)

    if args.dry_run:
        _print_case_list(cases)
        return 0

    if args.check_imports:
        _check_imports()
        print("OK: turn pipeline probe imports resolved without runtime construction")
        return 0

    if not args.account_id:
        parser.error(
            "--account-id is required unless --check-imports or --dry-run is used"
        )
    try:
        UUID(args.account_id)
    except ValueError:
        parser.error("--account-id must be a UUID string")

    return run_probe(
        account_id=args.account_id,
        cases=cases,
        default_timezone=args.default_timezone,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the turn pipeline parity probe against the composed Coke "
            "runtime without closing turns or sending delivery."
        )
    )
    parser.add_argument(
        "--account-id",
        help="Synthetic test account UUID used as trusted account context.",
    )
    parser.add_argument(
        "--default-timezone",
        default="Asia/Tokyo",
        help="Trusted default timezone injected into TurnPipelineRequest.",
    )
    parser.add_argument(
        "--required-only",
        action="store_true",
        help="Run only the corpus explicitly requested in the harness brief.",
    )
    parser.add_argument(
        "--check-imports",
        action="store_true",
        help="Import the script and turn pipeline symbols without building Settings or runtime.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the corpus and exit without importing Coke runtime modules.",
    )
    return parser


def _check_imports() -> None:
    from coke.composition import Settings, build_runtime_from_settings
    from coke.turn.inbound.express import ExpressRequest
    from coke.turn.inbound.pipeline import (
        TurnPipelineRequest,
        _action_context,
        _plan_request,
    )

    symbols = (
        Settings,
        build_runtime_from_settings,
        ExpressRequest,
        TurnPipelineRequest,
        _action_context,
        _plan_request,
    )
    if not all(symbols):
        raise RuntimeError("turn pipeline probe import check failed")


def run_probe(
    *,
    account_id: str,
    cases: Sequence[ProbeCase],
    default_timezone: str,
) -> int:
    from coke.composition import Settings, build_runtime_from_settings

    try:
        settings = Settings.from_env()
    except Exception as error:
        print(f"ERROR: Settings.from_env() failed: {error}", file=sys.stderr)
        return 2
    if settings.llm_fake:
        print(
            "ERROR: COKE_LLM_FAKE is enabled; this probe requires the real GLM path.",
            file=sys.stderr,
        )
        return 2

    runtime = None
    cleanup_messages: list[str] = []
    cleanup_errors: list[str] = []
    created_reminder_ids: list[str] = []
    setup_failures: list[str] = []

    try:
        runtime = build_runtime_from_settings(settings)
    except Exception as error:
        print(f"ERROR: build_runtime_from_settings() failed: {error}", file=sys.stderr)
        return 2

    pipeline = runtime.turn_pipeline
    if pipeline is None:
        print("SKIP: build_runtime_from_settings() returned no turn_pipeline")
        _close_runtime(runtime)
        return 2

    results: list[ProbeResult] = []
    try:
        print("SETUP")
        for case in SETUP_CASES:
            try:
                setup_result = _run_one_path(
                    pipeline=pipeline,
                    account_id=account_id,
                    case=case,
                    default_timezone=default_timezone,
                    render=False,
                )
                ids = _created_reminder_ids(setup_result.settled_outcome)
                created_reminder_ids.extend(ids)
                status = _first_outcome_status(setup_result.settled_outcome)
                print(
                    f"- {case.name}: plan={_actions_label(setup_result.plan)} "
                    f"outcome={status} created={','.join(ids) or '-'}"
                )
            except Exception:
                detail = traceback.format_exc(limit=8)
                setup_failures.append(f"{case.name}: {detail}")
                print(f"- {case.name}: exception")
        _flush_session(runtime)

        for index, case in enumerate(cases, start=1):
            nested = _begin_nested(runtime)
            try:
                raw = _run_one_path(
                    pipeline=pipeline,
                    account_id=account_id,
                    case=case,
                    default_timezone=default_timezone,
                    render=True,
                    turn_index=index,
                )
                results.append(_evaluate_result(case, raw))
            except Exception:
                results.append(
                    ProbeResult(
                        case=case,
                        exception=traceback.format_exc(limit=8),
                        passed=False,
                        notes=("exception",),
                    )
                )
            finally:
                _rollback_nested(nested)
    finally:
        cleanup_messages, cleanup_errors = _cleanup_created_reminders(
            runtime,
            account_id=account_id,
            reminder_ids=created_reminder_ids,
        )
        _close_runtime(runtime)

    _print_matrix(results)
    passed = sum(1 for result in results if result.passed)
    total = len(results)
    print()
    print(f"{passed}/{total} paths PASS")
    if cleanup_messages:
        print("CLEANUP")
        for message in cleanup_messages:
            print(f"- {message}")
    if cleanup_errors:
        print("CLEANUP FAILURES")
        for message in cleanup_errors:
            print(f"- {message}")
    if setup_failures:
        print("SETUP FAILURES")
        for failure in setup_failures:
            print(f"- {failure}")
    _print_failures(results)
    return 0 if passed == total and not cleanup_errors and not setup_failures else 1


def _run_one_path(
    *,
    pipeline: Any,
    account_id: str,
    case: ProbeCase,
    default_timezone: str,
    render: bool,
    turn_index: int = 0,
) -> RawPathResult:
    from coke.turn.inbound.express import ExpressRequest
    from coke.turn.inbound.pipeline import (
        TurnPipelineRequest,
        _action_context,
        _plan_request,
    )

    turn_id = f"turn-pipeline-probe-{turn_index}-{uuid4().hex[:12]}"
    conversation_id = f"turn-pipeline-probe-conversation-{account_id}"
    now = datetime.now(UTC)
    payload = {
        "text": case.message,
        "message": case.message,
        "probe_case": case.name,
    }
    request = TurnPipelineRequest(
        turn_id=turn_id,
        account_id=account_id,
        conversation_id=conversation_id,
        payload=payload,
        trusted_facts={
            "account_id": account_id,
            "default_timezone": default_timezone,
            "timezone": default_timezone,
        },
        conversation_history=(
            {"role": "user", "content": case.message, "created_at": now.isoformat()},
        ),
        now=now,
        run_id=turn_id,
    )
    plan = pipeline._planner.plan(_plan_request(request, None))
    compiled = pipeline._compile(plan)
    guard = RecordingGuard(turn_id)
    settled_outcome = pipeline._executor.execute(
        compiled,
        guard,
        _action_context(request),
    )
    segments: tuple[str, ...] = ()
    if render and plan.reply_necessity != "intentional_no_reply":
        segments = tuple(
            pipeline._express.render(
                ExpressRequest(
                    turn_id=request.turn_id,
                    conversation_id=request.conversation_id,
                    account_id=request.account_id,
                    settled_outcome=settled_outcome,
                    conversation_history=request.conversation_history,
                    persona=request.persona,
                    assistant_name=request.assistant_name,
                    user_address_name=request.user_address_name,
                    payload=request.payload,
                    run_id=request.run_id,
                )
            )
        )
    return RawPathResult(
        plan=plan,
        compiled=compiled,
        settled_outcome=settled_outcome,
        segments=segments,
        state_change_calls=guard.state_change_calls,
    )


def _evaluate_result(case: ProbeCase, raw: RawPathResult) -> ProbeResult:
    plan_actions = tuple(
        (action.domain, action.operation) for action in getattr(raw.plan, "actions", ())
    )
    compiled_actions = tuple(getattr(raw.compiled, "actions", ()))
    compiled_ok = all(
        getattr(action, "category", None) is None for action in compiled_actions
    )
    first_outcome = _first_outcome(raw.settled_outcome)
    category = getattr(first_outcome, "category", None)
    status = getattr(first_outcome, "status", None)

    notes: list[str] = []
    plan_ok = _plan_matches(case, plan_actions)
    if not plan_ok:
        notes.append("planner_mismatch")
    category_ok = _category_matches(case, category, status)
    if not category_ok:
        notes.append("unexpected_outcome")
    express_ok = (
        bool(raw.segments)
        if getattr(raw.plan, "reply_necessity", None) != "intentional_no_reply"
        else True
    )
    if not express_ok:
        notes.append("express_empty")
    if not compiled_ok:
        notes.append("compiled_blocked")

    return ProbeResult(
        case=case,
        plan_actions=plan_actions,
        plan_payload=_plain_value(raw.plan),
        compiled_ok=compiled_ok,
        compiled_payload=_plain_value(raw.compiled),
        outcome_category=category,
        outcome_status=status,
        outcome_payload=_plain_value(raw.settled_outcome),
        segments=raw.segments,
        state_change_calls=raw.state_change_calls,
        passed=plan_ok and category_ok and express_ok,
        notes=tuple(notes),
    )


def _plan_matches(case: ProbeCase, plan_actions: tuple[tuple[str, str], ...]) -> bool:
    if case.expect_domain is None and case.expect_op is None:
        return not plan_actions
    return bool(plan_actions) and plan_actions[0] == (
        case.expect_domain,
        case.expect_op,
    )


def _category_matches(
    case: ProbeCase,
    category: str | None,
    status: str | None,
) -> bool:
    if case.expect_domain is None and case.expect_op is None:
        return category is None
    if category == "not_possible":
        return bool(status and status in case.allowed_not_possible_statuses)
    allowed = frozenset(case.expect_categories or tuple(SENSIBLE_CATEGORIES))
    return bool(category and category in allowed)


def _created_reminder_ids(settled_outcome: Any) -> list[str]:
    ids: list[str] = []
    for outcome in getattr(settled_outcome, "outcomes", ()):
        data = getattr(outcome, "data", {}) or {}
        items = data.get("items") if isinstance(data, Mapping) else None
        if isinstance(items, list):
            for item in items:
                if isinstance(item, Mapping) and item.get("state") == "succeeded":
                    reminder_id = item.get("reminder_id")
                    if isinstance(reminder_id, str) and reminder_id:
                        ids.append(reminder_id)
        reminder_id = data.get("reminder_id") if isinstance(data, Mapping) else None
        if isinstance(reminder_id, str) and reminder_id:
            ids.append(reminder_id)
    return list(dict.fromkeys(ids))


def _cleanup_created_reminders(
    runtime: Any,
    *,
    account_id: str,
    reminder_ids: Sequence[str],
) -> tuple[list[str], list[str]]:
    messages: list[str] = []
    errors: list[str] = []
    unique_ids = list(dict.fromkeys(reminder_ids))
    if not unique_ids:
        _rollback_session(runtime)
        return ["no setup reminders were created; rolled back open transaction"], []
    guard = RecordingGuard(f"turn-pipeline-probe-cleanup-{uuid4().hex[:12]}")
    for reminder_id in unique_ids:
        try:
            runtime.reminder_service.delete_reminder(
                account_id,
                reminder_id,
                user_initiated=False,
                commit_guard=guard.guard_state_change,
            )
            messages.append(f"soft-deleted setup reminder {reminder_id}")
        except Exception as error:
            errors.append(f"{reminder_id}: {error}")
    if errors:
        _rollback_session(runtime)
        messages.append("cleanup failed; rolled back open transaction")
        return messages, errors
    try:
        _flush_session(runtime)
        runtime.session.commit()
        messages.append("committed cleanup transaction")
    except Exception as error:
        _rollback_session(runtime)
        errors.append(f"commit cleanup transaction: {error}")
    return messages, errors


def _begin_nested(runtime: Any) -> Any:
    session = getattr(runtime, "session", None)
    if session is None:
        return None
    return session.begin_nested()


def _rollback_nested(nested: Any) -> None:
    if nested is None:
        return
    try:
        if getattr(nested, "is_active", False):
            nested.rollback()
    except Exception:
        pass


def _flush_session(runtime: Any) -> None:
    session = getattr(runtime, "session", None)
    if session is not None:
        session.flush()


def _rollback_session(runtime: Any) -> None:
    session = getattr(runtime, "session", None)
    if session is not None:
        session.rollback()


def _close_runtime(runtime: Any) -> None:
    session = getattr(runtime, "session", None)
    if session is not None:
        session.close()
    engine = getattr(runtime, "engine", None)
    if engine is not None:
        engine.dispose()
    redis_client = getattr(runtime, "redis_client", None)
    close = getattr(redis_client, "close", None)
    if callable(close):
        close()


def _first_outcome(settled_outcome: Any) -> Any | None:
    outcomes = getattr(settled_outcome, "outcomes", ())
    return outcomes[0] if outcomes else None


def _first_outcome_status(settled_outcome: Any) -> str:
    outcome = _first_outcome(settled_outcome)
    if outcome is None:
        return "none"
    return f"{getattr(outcome, 'category', '?')}.{getattr(outcome, 'status', '?')}"


def _actions_label(plan: Any) -> str:
    actions = getattr(plan, "actions", ())
    if not actions:
        return "none"
    return ",".join(f"{action.domain}.{action.operation}" for action in actions)


def _plain_value(value: Any) -> Any:
    # NOTE: do not use dataclasses.asdict — it deep-copies and chokes on the
    # frozen dataclasses' MappingProxyType params ("cannot pickle 'mappingproxy'").
    # Walk fields manually instead.
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_value(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _print_case_list(cases: Sequence[ProbeCase]) -> None:
    print("CORPUS")
    for case in cases:
        expected = (
            "converse"
            if case.expect_domain is None
            else f"{case.expect_domain}.{case.expect_op}"
        )
        print(f"- {case.name}: {case.message} -> {expected}")


def _print_matrix(results: Sequence[ProbeResult]) -> None:
    headers = ("CASE", "EXPECT", "PLAN", "COMPILED", "OUTCOME", "EXP", "STATE", "PASS")
    rows = []
    for result in results:
        expected = (
            "converse"
            if result.case.expect_domain is None
            else f"{result.case.expect_domain}.{result.case.expect_op}"
        )
        planned = (
            ",".join(f"{domain}.{op}" for domain, op in result.plan_actions) or "-"
        )
        outcome = (
            f"{result.outcome_category}.{result.outcome_status}"
            if result.outcome_category
            else "-"
        )
        rows.append(
            (
                result.case.name,
                expected,
                planned,
                "yes" if result.compiled_ok else "no",
                outcome,
                str(len(result.segments)),
                str(result.state_change_calls),
                "PASS" if result.passed else "FAIL",
            )
        )
    widths = [
        min(max(len(str(row[index])) for row in (headers, *rows)), 34)
        for index in range(len(headers))
    ]
    print()
    print("MATRIX")
    print(_table_row(headers, widths))
    print(_table_sep(widths))
    for row in rows:
        print(_table_row(row, widths))


def _table_row(row: Sequence[str], widths: Sequence[int]) -> str:
    return " | ".join(
        _clip(str(value), width).ljust(width)
        for value, width in zip(row, widths, strict=True)
    )


def _table_sep(widths: Sequence[int]) -> str:
    return "-+-".join("-" * width for width in widths)


def _clip(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: max(0, width - 3)] + "..."


def _print_failures(results: Sequence[ProbeResult]) -> None:
    failures = [result for result in results if not result.passed]
    if not failures:
        return
    print()
    print("FAILURES")
    for result in failures:
        print(f"\n## {result.case.name}")
        print(f"message: {result.case.message}")
        print(f"expected: {result.case.expect_domain}.{result.case.expect_op}")
        print(f"notes: {', '.join(result.notes) or '-'}")
        detail = {
            "planner_actions": result.plan_actions,
            "plan": result.plan_payload,
            "compiled_ok": result.compiled_ok,
            "compiled": result.compiled_payload,
            "outcome": result.outcome_payload,
            "segments": list(result.segments),
            "state_change_calls": result.state_change_calls,
            "exception": result.exception,
        }
        print(json.dumps(detail, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
