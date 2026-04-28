#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import contextlib
import contextvars
import copy
import json
import multiprocessing
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import patch
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.reminder.models import ReminderFireResult
from agent.reminder.service import ReminderService
from agent.runner.reminder_scheduler import ReminderScheduler
from util.time_util import timestamp2str

DEFAULT_CASES_PATH = Path("scripts/reminder_test_cases.json")
DEFAULT_CHARACTER_ID = "reminder-e2e-character"
DEFAULT_PLATFORM = "wechat"
DEFAULT_ROUTE_KEY = "terminal:reminder-e2e"

_current_runtime: contextvars.ContextVar["CaseRuntime | None"] = contextvars.ContextVar(
    "reminder_e2e_runtime",
    default=None,
)


@dataclass(frozen=True)
class ReminderE2ECase:
    input: str
    expected_intent: str
    matched_keywords: list[str]
    metadata: dict[str, Any]


@dataclass
class ReminderE2EResult:
    index: int
    input: str
    user_id: str
    conversation_id: str
    passed: bool
    errors: list[str]
    user_outputs: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    created_reminders: list[dict[str, Any]]
    reminder_operations: list[dict[str, Any]]
    fire_events: list[dict[str, Any]]
    elapsed_seconds: float
    is_rollback: bool = False
    is_content_blocked: bool = False
    exception: str | None = None


class InMemoryReminderDAO:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.operations: list[dict[str, Any]] = []
        self.next_id = 1

    def insert_reminder(self, document: dict[str, Any]) -> str:
        reminder_id = f"rem-{self.next_id}"
        self.next_id += 1
        stored = copy.deepcopy(document)
        stored["_id"] = reminder_id
        self.documents[reminder_id] = stored
        self.operations.append({"op": "insert", "reminder_id": reminder_id})
        return reminder_id

    def get_reminder(self, reminder_id: str) -> dict[str, Any] | None:
        document = self.documents.get(reminder_id)
        return copy.deepcopy(document) if document else None

    def get_reminder_for_owner(
        self,
        reminder_id: str,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        document = self.documents.get(reminder_id)
        if document is None or document["owner_user_id"] != owner_user_id:
            return None
        return copy.deepcopy(document)

    def list_for_owner(
        self,
        owner_user_id: str,
        lifecycle_states: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        documents = [
            copy.deepcopy(document)
            for document in self.documents.values()
            if document["owner_user_id"] == owner_user_id
        ]
        if lifecycle_states is not None:
            documents = [
                document
                for document in documents
                if document["lifecycle_state"] in lifecycle_states
            ]
        return sorted(documents, key=lambda item: str(item["_id"]))

    def list_due_active(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(document)
            for document in sorted(
                self.documents.values(),
                key=lambda item: item.get("next_fire_at")
                or datetime.max.replace(tzinfo=UTC),
            )
            if document["lifecycle_state"] == "active"
            and document.get("next_fire_at") is not None
        ]

    def replace_reminder(
        self,
        reminder_id: str,
        owner_user_id: str,
        updates: dict[str, Any],
        lifecycle_state: str | None = None,
    ) -> bool:
        document = self.documents.get(reminder_id)
        if document is None or document["owner_user_id"] != owner_user_id:
            return False
        if lifecycle_state is not None and document["lifecycle_state"] != lifecycle_state:
            return False
        document.update(copy.deepcopy(updates))
        self.operations.append(
            {
                "op": "replace",
                "reminder_id": reminder_id,
                "updates": sorted(updates.keys()),
                "lifecycle_state": document.get("lifecycle_state"),
            }
        )
        return True

    def atomic_apply_fire_success(
        self,
        reminder_id: str,
        expected_next_fire_at: datetime,
        updates: dict[str, Any],
    ) -> bool:
        return self._atomic_apply_fire("fire_success", reminder_id, expected_next_fire_at, updates)

    def atomic_apply_fire_failure(
        self,
        reminder_id: str,
        expected_next_fire_at: datetime,
        updates: dict[str, Any],
    ) -> bool:
        return self._atomic_apply_fire("fire_failure", reminder_id, expected_next_fire_at, updates)

    def _atomic_apply_fire(
        self,
        op: str,
        reminder_id: str,
        expected_next_fire_at: datetime,
        updates: dict[str, Any],
    ) -> bool:
        document = self.documents.get(reminder_id)
        if (
            document is None
            or document["lifecycle_state"] != "active"
            or document["next_fire_at"] != expected_next_fire_at
        ):
            return False
        document.update(copy.deepcopy(updates))
        self.operations.append(
            {
                "op": op,
                "reminder_id": reminder_id,
                "updates": sorted(updates.keys()),
                "lifecycle_state": document.get("lifecycle_state"),
            }
        )
        return True


class RecordingSchedulerBackend:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        self.stopped = True

    def add_job(
        self,
        func,
        *,
        trigger,
        id,
        replace_existing,
        run_date,
        kwargs,
        misfire_grace_time,
    ):
        self.jobs[id] = {
            "func": func,
            "trigger": trigger,
            "replace_existing": replace_existing,
            "run_date": run_date,
            "kwargs": kwargs,
            "misfire_grace_time": misfire_grace_time,
        }

    def remove_job(self, job_id: str) -> None:
        if job_id not in self.jobs:
            raise JobLookupError(job_id)
        del self.jobs[job_id]


class FakeLockManager:
    def renew_lock(self, *_args, **_kwargs) -> bool:
        return True

    def get_lock_info(self, *_args, **_kwargs) -> dict[str, str] | None:
        return None


@dataclass
class CaseRuntime:
    case_index: int
    now: datetime
    reminder_dao: InMemoryReminderDAO = field(default_factory=InMemoryReminderDAO)
    scheduler_backend: RecordingSchedulerBackend = field(
        default_factory=RecordingSchedulerBackend
    )
    outputs: list[dict[str, Any]] = field(default_factory=list)
    fire_events: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.scheduler = ReminderScheduler(
            reminder_dao=self.reminder_dao,
            fire_event_handler=self._fire_event,
            scheduler=self.scheduler_backend,
            now_provider=lambda: self.now,
        )
        self.service = ReminderService(
            reminder_dao=self.reminder_dao,
            scheduler=self.scheduler,
            now_provider=lambda: self.now,
        )

    @property
    def created_reminders(self) -> list[dict[str, Any]]:
        return list(self.reminder_dao.documents.values())

    async def _fire_event(self, event) -> ReminderFireResult:
        self.fire_events.append(
            {
                "fire_id": event.fire_id,
                "reminder_id": event.reminder_id,
                "owner_user_id": event.owner_user_id,
                "title": event.title,
                "scheduled_for": event.scheduled_for,
                "fire_at": event.fire_at,
            }
        )
        return ReminderFireResult(
            ok=True,
            fire_id=event.fire_id,
            output_reference=f"reminder-e2e-output-{self.case_index}",
            error_code=None,
            error_message=None,
        )


def current_case_runtime() -> CaseRuntime:
    runtime = _current_runtime.get()
    if runtime is None:
        raise RuntimeError("no current reminder E2E runtime")
    return runtime


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[ReminderE2ECase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        ReminderE2ECase(
            input=str(item["input"]),
            expected_intent=str(item.get("expected_intent", "")),
            matched_keywords=list(item.get("matched_keywords") or []),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in data["test_cases"]
    ]


def select_cases(
    cases: list[ReminderE2ECase],
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[ReminderE2ECase]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    selected = cases[offset:]
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        selected = selected[:limit]
    return selected


def case_now(case: ReminderE2ECase, *, timezone: str) -> datetime:
    timestamp = str(case.metadata.get("timestamp") or "").strip()
    tz = ZoneInfo(timezone)
    if timestamp:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    return datetime.now(tz)


def build_case_context(
    case: ReminderE2ECase,
    *,
    index: int,
    timezone: str,
    character_id: str = DEFAULT_CHARACTER_ID,
    platform: str = DEFAULT_PLATFORM,
) -> dict[str, Any]:
    now = case_now(case, timezone=timezone)
    timestamp = int(now.timestamp())
    user_id = str(case.metadata.get("from_user") or f"reminder-e2e-user-{index}")
    conversation_id = str(case.metadata.get("source_id") or f"reminder-e2e-conv-{index}")
    input_message = {
        "_id": f"reminder-e2e-input-{index}",
        "input_timestamp": timestamp,
        "handled_timestamp": timestamp,
        "status": "pending",
        "from_user": user_id,
        "platform": platform,
        "chatroom_name": None,
        "to_user": character_id,
        "message_type": "text",
        "message": case.input,
        "metadata": {
            "source": "reminder_e2e",
            "case_index": index,
            "source_id": conversation_id,
            "from_user": user_id,
        },
    }
    time_str = timestamp2str(timestamp, week=False, tz=ZoneInfo(timezone))
    input_messages_str = f"{user_id}: {case.input}"
    return {
        "user": {
            "_id": user_id,
            "id": user_id,
            "nickname": f"terminal-user-{user_id[-6:]}",
            "name": f"terminal-user-{user_id[-6:]}",
            "effective_timezone": timezone,
        },
        "character": {
            "_id": character_id,
            "id": character_id,
            "nickname": "ReminderE2E",
            "name": "ReminderE2E",
            "user_info": {
                "description": "You help users manage reminders.",
                "status": {"place": "测试环境", "action": "回复消息"},
            },
        },
        "conversation": {
            "_id": conversation_id,
            "id": conversation_id,
            "platform": platform,
            "chatroom_name": None,
            "conversation_info": {
                "chat_history": [],
                "chat_history_str": "",
                "input_messages": [input_message],
                "input_messages_str": input_messages_str,
                "photo_history": [],
                "time_str": time_str,
                "turn_sent_contents": [],
            },
        },
        "platform": platform,
        "input_timestamp": timestamp,
        "delivery_route_key": DEFAULT_ROUTE_KEY,
        "route_key": DEFAULT_ROUTE_KEY,
        "relation": {
            "relationship": {"closeness": 20, "trustness": 20, "dislike": 0, "status": "空闲"},
            "user_info": {"realname": "", "hobbyname": "", "description": ""},
            "character_info": {
                "longterm_purpose": "",
                "shortterm_purpose": "",
                "attitude": "",
            },
        },
        "context_retrieve": _default_context_retrieve(),
        "query_rewrite": {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": "",
        },
        "MultiModalResponses": [],
        "group_chat_context": "",
        "news_str": "",
        "is_new_user": False,
        "repeated_input_notice": "",
        "proactive_forbidden_messages": [],
    }


def validate_case_observations(
    case: ReminderE2ECase,
    runtime: CaseRuntime,
    *,
    user_outputs: list[dict[str, Any]],
    is_rollback: bool,
    is_content_blocked: bool,
) -> list[str]:
    errors: list[str] = []
    if not user_outputs:
        errors.append("no_user_output")
    if is_rollback:
        errors.append("rollback")
    if is_content_blocked:
        errors.append("content_blocked")
    if case.expected_intent == "reminder" and not (
        runtime.tool_results or runtime.reminder_dao.operations
    ):
        errors.append("tool_not_called")
    for document in runtime.created_reminders:
        next_fire_at = document.get("next_fire_at")
        if next_fire_at is None:
            errors.append("created_reminder_missing_next_fire_at")
        elif next_fire_at <= runtime.now:
            errors.append("created_reminder_not_in_future")
        schedule = document.get("schedule") or {}
        rrule = schedule.get("rrule")
        if rrule is not None and not str(rrule).startswith("FREQ="):
            errors.append("invalid_rrule")
    return errors


async def validate_trigger_delivery(runtime: CaseRuntime) -> list[str]:
    errors: list[str] = []
    active_reminders = [
        copy.deepcopy(document)
        for document in runtime.created_reminders
        if document.get("lifecycle_state") == "active"
        and document.get("next_fire_at") is not None
    ]
    for document in active_reminders:
        reminder_id = str(document["_id"])
        next_fire_at = document["next_fire_at"]
        runtime.now = _ensure_aware_utc(next_fire_at) + timedelta(seconds=1)
        before_events = len(runtime.fire_events)
        await runtime.scheduler._execute_job(reminder_id, next_fire_at)
        stored = runtime.reminder_dao.documents[reminder_id]
        if len(runtime.fire_events) != before_events + 1:
            errors.append("scheduler_fire_failure")
        if stored.get("lifecycle_state") == "active":
            if stored.get("next_fire_at") is None:
                errors.append("recurring_reminder_missing_next_fire_at")
        elif stored.get("lifecycle_state") != "completed":
            errors.append("scheduler_fire_terminal_state_invalid")
    return errors


HandleMessageFunc = Callable[..., Awaitable[tuple[list[dict], dict, bool, bool]]]


async def run_case(
    case: ReminderE2ECase,
    *,
    index: int,
    timezone: str,
    case_timeout_seconds: float,
    handle_message_func: HandleMessageFunc | None = None,
    validate_triggers: bool = True,
) -> ReminderE2EResult:
    started = time.monotonic()
    now = case_now(case, timezone=timezone).astimezone(UTC)
    runtime = CaseRuntime(case_index=index, now=now)
    context = build_case_context(case, index=index, timezone=timezone)
    token = _current_runtime.set(runtime)
    outputs: list[dict[str, Any]] = []
    is_rollback = False
    is_content_blocked = False
    exception: str | None = None
    try:
        if handle_message_func is None:
            from agent.runner.agent_handler import handle_message as handle_message_func

        outputs, context, is_rollback, is_content_blocked = await asyncio.wait_for(
            handle_message_func(
                context,
                case.input,
                message_source="user",
                check_new_message=False,
                worker_tag=f"[ReminderE2E:{index}]",
                conversation_id=context["conversation"]["_id"],
                current_message_ids=[
                    str(message["_id"])
                    for message in context["conversation"]["conversation_info"][
                        "input_messages"
                    ]
                ],
            ),
            timeout=case_timeout_seconds,
        )
        runtime.tool_results = list(context.get("tool_results") or [])
        errors = validate_case_observations(
            case,
            runtime,
            user_outputs=outputs or runtime.outputs,
            is_rollback=is_rollback,
            is_content_blocked=is_content_blocked,
        )
        if validate_triggers:
            errors.extend(await validate_trigger_delivery(runtime))
    except Exception as exc:
        exception = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        errors = ["exception"]
    finally:
        _current_runtime.reset(token)

    return ReminderE2EResult(
        index=index,
        input=case.input,
        user_id=context["user"]["id"],
        conversation_id=context["conversation"]["_id"],
        passed=not errors,
        errors=errors,
        user_outputs=outputs or runtime.outputs,
        tool_results=runtime.tool_results,
        created_reminders=runtime.created_reminders,
        reminder_operations=runtime.reminder_dao.operations,
        fire_events=runtime.fire_events,
        elapsed_seconds=round(time.monotonic() - started, 3),
        is_rollback=is_rollback,
        is_content_blocked=is_content_blocked,
        exception=exception,
    )


async def run_eval(
    cases: list[ReminderE2ECase],
    *,
    offset: int,
    limit: int | None,
    timezone: str,
    concurrency: int,
    case_timeout_seconds: float,
    handle_message_func: HandleMessageFunc | None = None,
    validate_triggers: bool = True,
) -> list[ReminderE2EResult]:
    selected = select_cases(cases, offset=offset, limit=limit)
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(local_index: int, case: ReminderE2ECase) -> ReminderE2EResult:
        async with semaphore:
            return await run_case(
                case,
                index=offset + local_index,
                timezone=timezone,
                case_timeout_seconds=case_timeout_seconds,
                handle_message_func=handle_message_func,
                validate_triggers=validate_triggers,
            )

    with patched_runtime_boundaries(patch_agent_handler=handle_message_func is None):
        return await asyncio.gather(
            *(guarded(local_index, case) for local_index, case in enumerate(selected))
        )


async def run_eval_in_processes(
    cases: list[ReminderE2ECase],
    *,
    offset: int,
    limit: int | None,
    timezone: str,
    concurrency: int,
    case_timeout_seconds: float,
    validate_triggers: bool = True,
) -> list[ReminderE2EResult]:
    selected = select_cases(cases, offset=offset, limit=limit)
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(local_index: int, case: ReminderE2ECase) -> ReminderE2EResult:
        async with semaphore:
            return await run_case_in_process_async(
                case,
                index=offset + local_index,
                timezone=timezone,
                case_timeout_seconds=case_timeout_seconds,
                validate_triggers=validate_triggers,
            )

    return await asyncio.gather(
        *(guarded(local_index, case) for local_index, case in enumerate(selected))
    )


async def run_case_in_process_async(
    case: ReminderE2ECase,
    *,
    index: int,
    timezone: str,
    case_timeout_seconds: float,
    validate_triggers: bool = True,
) -> ReminderE2EResult:
    queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=1)
    process = multiprocessing.Process(
        target=_case_process_entrypoint,
        args=(
            queue,
            asdict(case),
            index,
            timezone,
            case_timeout_seconds,
            validate_triggers,
        ),
    )
    started = time.monotonic()
    process.start()
    while process.is_alive() and time.monotonic() - started < case_timeout_seconds:
        await asyncio.sleep(0.05)
    return _finish_case_process(
        case,
        process=process,
        queue=queue,
        index=index,
        elapsed_seconds=time.monotonic() - started,
        timed_out=process.is_alive(),
    )


def run_case_in_process(
    case: ReminderE2ECase,
    *,
    index: int,
    timezone: str,
    case_timeout_seconds: float,
    validate_triggers: bool = True,
) -> ReminderE2EResult:
    queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=1)
    process = multiprocessing.Process(
        target=_case_process_entrypoint,
        args=(
            queue,
            asdict(case),
            index,
            timezone,
            case_timeout_seconds,
            validate_triggers,
        ),
    )
    started = time.monotonic()
    process.start()
    process.join(case_timeout_seconds)
    return _finish_case_process(
        case,
        process=process,
        queue=queue,
        index=index,
        elapsed_seconds=time.monotonic() - started,
        timed_out=process.is_alive(),
    )


def _finish_case_process(
    case: ReminderE2ECase,
    *,
    process: multiprocessing.Process,
    queue: multiprocessing.Queue,
    index: int,
    elapsed_seconds: float,
    timed_out: bool,
) -> ReminderE2EResult:
    if timed_out:
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        return _timeout_result(
            case,
            index=index,
            elapsed_seconds=elapsed_seconds,
        )
    if not queue.empty():
        payload = queue.get()
        return ReminderE2EResult(**payload)
    if process.exitcode == 0:
        return _timeout_result(
            case,
            index=index,
            elapsed_seconds=elapsed_seconds,
            errors=["missing_process_result"],
        )
    return _timeout_result(
        case,
        index=index,
        elapsed_seconds=elapsed_seconds,
        errors=["process_failed"],
        exception=f"process exited with code {process.exitcode}",
    )


def run_process_timeout_probe(*, timeout_seconds: float) -> str:
    queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=1)
    process = multiprocessing.Process(target=_blocking_timeout_probe, args=(queue,))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        return "timeout"
    return str(queue.get()) if not queue.empty() else "exited"


def _blocking_timeout_probe(queue: multiprocessing.Queue) -> None:
    time.sleep(60)
    queue.put("completed")


def _case_process_entrypoint(
    queue: multiprocessing.Queue,
    case_payload: dict[str, Any],
    index: int,
    timezone: str,
    case_timeout_seconds: float,
    validate_triggers: bool,
) -> None:
    case = ReminderE2ECase(**case_payload)
    with patched_runtime_boundaries():
        result = asyncio.run(
            run_case(
                case,
                index=index,
                timezone=timezone,
                case_timeout_seconds=case_timeout_seconds,
                validate_triggers=validate_triggers,
            )
        )
    queue.put(asdict(result))


def _timeout_result(
    case: ReminderE2ECase,
    *,
    index: int,
    elapsed_seconds: float,
    errors: list[str] | None = None,
    exception: str | None = "case exceeded hard process timeout",
) -> ReminderE2EResult:
    user_id = str(case.metadata.get("from_user") or f"reminder-e2e-user-{index}")
    conversation_id = str(
        case.metadata.get("source_id") or f"reminder-e2e-conv-{index}"
    )
    return ReminderE2EResult(
        index=index,
        input=case.input,
        user_id=user_id,
        conversation_id=conversation_id,
        passed=False,
        errors=errors or ["case_timeout"],
        user_outputs=[],
        tool_results=[],
        created_reminders=[],
        reminder_operations=[],
        fire_events=[],
        elapsed_seconds=round(elapsed_seconds, 3),
        exception=exception,
    )


@contextlib.contextmanager
def patched_runtime_boundaries(*, patch_agent_handler: bool = True):
    patches = [
        patch("dao.lock.MongoDBLockManager", FakeLockManager),
        patch(
            "agent.agno_agent.tools.reminder_protocol.tool.ReminderService",
            _runtime_reminder_service_factory,
        ),
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool",
            _fake_context_retrieve_tool,
        ),
        patch(
            "agent.agno_agent.workflows.prepare_workflow.usage_tracker.record_from_metrics",
            _record_usage_noop,
        ),
    ]
    if patch_agent_handler:
        patches.extend(
            [
                patch(
                    "agent.runner.agent_handler.send_message_via_context",
                    _record_output_message,
                ),
                patch(
                    "agent.runner.agent_handler.is_new_message_coming_in",
                    lambda *_args, **_kwargs: False,
                ),
            ]
        )
    previous_skip_post_analyze = os.environ.get("SKIP_POST_ANALYZE")
    os.environ["SKIP_POST_ANALYZE"] = "1"
    try:
        for item in patches:
            item.start()
        yield
    finally:
        for item in reversed(patches):
            item.stop()
        if previous_skip_post_analyze is None:
            os.environ.pop("SKIP_POST_ANALYZE", None)
        else:
            os.environ["SKIP_POST_ANALYZE"] = previous_skip_post_analyze


def summarize(results: list[ReminderE2EResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failures = [result for result in results if not result.passed]
    by_error: dict[str, int] = {}
    for result in failures:
        for error in result.errors:
            by_error[error] = by_error.get(error, 0) + 1
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0,
        "by_error": dict(sorted(by_error.items())),
        "failures": [asdict(result) for result in failures],
    }


def _runtime_reminder_service_factory() -> ReminderService:
    return current_case_runtime().service


def _record_output_message(
    context: dict[str, Any],
    message: str,
    message_type: str = "text",
    expect_output_timestamp: int | None = None,
    metadata: dict[str, Any] | None = None,
    **_kwargs,
) -> dict[str, Any]:
    runtime = current_case_runtime()
    user_id = str(context.get("user", {}).get("id") or context.get("user", {}).get("_id"))
    character_id = str(
        context.get("character", {}).get("id")
        or context.get("character", {}).get("_id")
    )
    output = {
        "_id": f"reminder-e2e-output-{runtime.case_index}-{len(runtime.outputs) + 1}",
        "platform": context.get("platform") or context.get("conversation", {}).get("platform"),
        "from_user": character_id,
        "to_user": user_id,
        "message": message,
        "message_type": message_type,
        "status": "handled",
        "expect_output_timestamp": expect_output_timestamp or int(time.time()),
        "metadata": metadata or {},
    }
    runtime.outputs.append(output)
    return output


def _fake_context_retrieve_tool(**_kwargs) -> dict[str, str]:
    return _default_context_retrieve()


def _record_usage_noop(*_args, **_kwargs):
    return None


def _default_context_retrieve() -> dict[str, str]:
    return {
        "character_global": "",
        "character_private": "",
        "user": "",
        "character_knowledge": "",
        "confirmed_reminders": "",
        "relevant_history": "",
    }


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run class-E2E reminder tests over real user reminder inputs. "
            "Each case simulates a distinct terminal-style user/conversation, "
            "captures user-visible outputs, records reminder CRUD, and virtually "
            "fires created reminders without waiting for wall-clock time."
        )
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--case-timeout-seconds", type=float, default=90)
    parser.add_argument(
        "--case-isolation",
        choices=("process", "in-process"),
        default="process",
    )
    parser.add_argument("--no-trigger-validation", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def _amain() -> int:
    args = _parse_args()
    runner = run_eval_in_processes if args.case_isolation == "process" else run_eval
    results = await runner(
        load_cases(args.cases),
        offset=args.offset,
        limit=args.limit,
        timezone=args.timezone,
        concurrency=args.concurrency,
        case_timeout_seconds=args.case_timeout_seconds,
        validate_triggers=not args.no_trigger_validation,
    )
    payload = {
        "cases": str(args.cases),
        "offset": args.offset,
        "limit": args.limit,
        "timezone": args.timezone,
        "concurrency": args.concurrency,
        "case_timeout_seconds": args.case_timeout_seconds,
        "case_isolation": args.case_isolation,
        "trigger_validation": not args.no_trigger_validation,
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["summary"]["failed"] == 0 else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
