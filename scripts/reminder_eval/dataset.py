from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CASES_PATH = Path("scripts/reminder_test_cases.json")
DEFAULT_EXPECTATIONS_PATH = Path("scripts/reminder_normal_path_expectations.json")
PENDING_WORKFLOW_TWO_TURN_CASE_NAME = "pending-workflow-hourly-checkin-two-turn"
PENDING_WORKFLOW_TWO_TURN_TURNS = (
    "每个整点喊我打卡吧",
    "从现在到晚上七点",
)
PENDING_WORKFLOW_TWO_TURN_GUARD_MODES = (
    "high_frequency_guards_enabled",
    "high_frequency_guards_bypassed",
)


@dataclass(frozen=True)
class ReminderNormalPathCase:
    input: str
    expected_intent: str
    matched_keywords: list[str]
    metadata: dict[str, Any]


@dataclass
class ReminderNormalPathResult:
    index: int
    input: str
    user_id: str
    original_from_user: str
    input_message_id: str
    input_status: str
    passed: bool
    errors: list[str]
    outputs: list[dict[str, Any]]
    reminders: list[dict[str, Any]]
    elapsed_seconds: float


@dataclass(frozen=True)
class CaseBatch:
    offset: int
    limit: int


@dataclass(frozen=True)
class ExpectedReminderCreate:
    title: str
    local_time: str | None
    recurring: bool | None
    local_date: str | None = None
    title_variants: tuple[str, ...] = ()
    rrule_contains: tuple[str, ...] = ()
    output_terms: tuple[str, ...] = ()


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[ReminderNormalPathCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    expectations = load_case_expectations(DEFAULT_EXPECTATIONS_PATH)
    return [
        ReminderNormalPathCase(
            input=str(item["input"]),
            expected_intent=str(item.get("expected_intent", "")),
            matched_keywords=list(item.get("matched_keywords") or []),
            metadata=merge_case_expectation_metadata(
                {
                    **dict(item.get("metadata") or {}),
                    "_case_index": index,
                },
                expectations.get(index, {}),
            ),
        )
        for index, item in enumerate(data["test_cases"])
    ]


def load_case_expectations(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases", data)
    return {int(index): dict(value) for index, value in raw_cases.items()}


def merge_case_expectation_metadata(
    metadata: dict[str, Any],
    expectation: dict[str, Any],
) -> dict[str, Any]:
    if not expectation:
        return metadata
    merged = dict(metadata)
    for key in (
        "evaluation_expectation",
        "evaluation_reason",
        "expected_operation",
        "allow_clarification",
        "expected_creates",
        "expected_clarification_terms",
    ):
        if key in expectation:
            merged[key] = expectation[key]
    return merged


def select_cases(
    cases: list[ReminderNormalPathCase],
    *,
    offset: int,
    limit: int | None,
) -> list[ReminderNormalPathCase]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    selected = cases[offset:]
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        selected = selected[:limit]
    return selected


def select_expectation_cases(
    cases: list[ReminderNormalPathCase],
) -> list[ReminderNormalPathCase]:
    return [
        case
        for case in cases
        if str(case.metadata.get("evaluation_expectation") or "").strip()
    ]


def pending_workflow_two_turn_eval_manifest() -> dict[str, Any]:
    return {
        "name": PENDING_WORKFLOW_TWO_TURN_CASE_NAME,
        "turns": list(PENDING_WORKFLOW_TWO_TURN_TURNS),
        "guard_modes": list(PENDING_WORKFLOW_TWO_TURN_GUARD_MODES),
        "transport": "business-clawscale",
        "expected_path": (
            "turn 1 persists an awaiting_user pending workflow; turn 2 loads "
            "the same workflow, advances it to execution, creates bounded "
            "reminders, and leaves the workflow terminal"
        ),
        "evidence_status": "open_real_model_business_clawscale_run_required",
    }


def runtime_case_index(case: ReminderNormalPathCase, fallback_index: int) -> int:
    try:
        return int(case.metadata.get("_case_index", fallback_index))
    except (TypeError, ValueError):
        return fallback_index


def iter_case_batches(
    *,
    total_count: int,
    offset: int,
    limit: int | None,
    batch_size: int,
):
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0")

    remaining_total = max(total_count - offset, 0)
    remaining = remaining_total if limit is None else min(limit, remaining_total)
    next_offset = offset
    while remaining > 0:
        next_limit = min(batch_size, remaining)
        yield CaseBatch(offset=next_offset, limit=next_limit)
        next_offset += next_limit
        remaining -= next_limit
