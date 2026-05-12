"""Phase 0: measure GLM-5.1 thinking-off raw time-math accuracy.

For each curated case with `expected_creates.local_time`, run GLM-5.1
*without* any of the Python time normalizers, extract the LLM's raw
trigger_at, convert to user-tz local time, and compare to expectation.

The question this answers: is the LLM strong enough at time math that
the 600 lines of `_normalize_*` / `_parse_chinese_*` / `_should_treat_*`
helpers in reminder_intent.py are over-engineering?
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_reminder_detect_models import (  # noqa: E402
    build_agent,
    build_context,
    decision_from_response,
    load_cases_and_expectations,
)

CANDIDATE = {
    "label": "glm-5.1-thinking-off-raw",
    "config": {
        "provider": "siliconflow",
        "model_id": "Pro/zai-org/GLM-5.1",
        "api_key": "${SiliconFlow_API_KEY}",
        "base_url": "https://api.siliconflow.cn/v1",
        "max_retries": 2,
        "extra_body": {"enable_thinking": False},
    },
}

TIMEZONE = "Asia/Tokyo"
TARGET_COUNT = 30
OUTPUT_PATH = PROJECT_ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy.json"


def select_time_cases(
    expectations: dict[int, dict[str, Any]],
    target: int,
) -> list[int]:
    """Pick cases with exactly one expected_create + concrete local_time."""
    picks: list[int] = []
    for idx in sorted(expectations.keys()):
        e = expectations[idx]
        if e.get("evaluation_expectation") != "crud":
            continue
        creates = e.get("expected_creates")
        if not isinstance(creates, list) or len(creates) != 1:
            continue
        create = creates[0]
        local_time = str(create.get("local_time") or "").strip()
        if not local_time or len(local_time) < 5:
            continue
        picks.append(idx)
        if len(picks) >= target:
            break
    return picks


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def local_hhmmss(dt: datetime, tz: str) -> str:
    return dt.astimezone(ZoneInfo(tz)).strftime("%H:%M:%S")


def grade_time(
    decision: dict[str, Any] | None,
    expected_local: str,
    tz: str,
) -> tuple[str, str | None, int | None]:
    if decision is None:
        return "fail_no_decision", None, None
    intent = str(decision.get("intent_type") or "").lower()
    if intent != "crud":
        return f"fail_intent_{intent}", None, None
    action = str(decision.get("action") or "").lower()
    if action == "batch":
        ops = decision.get("operations") or []
        if ops and isinstance(ops, list) and len(ops) >= 1:
            trigger_at = str(ops[0].get("trigger_at") or "")
        else:
            return "fail_batch_no_ops", None, None
    elif action == "create":
        trigger_at = str(decision.get("trigger_at") or "")
    else:
        return f"fail_action_{action}", None, None
    parsed = parse_iso(trigger_at)
    if parsed is None:
        return "fail_invalid_iso", trigger_at or None, None
    actual_local = local_hhmmss(parsed, tz)
    try:
        h, m, *rest = expected_local.split(":")
        exp_h, exp_m = int(h), int(m)
        a_h, a_m, *_ = actual_local.split(":")
        act_h, act_m = int(a_h), int(a_m)
        delta_min = abs((act_h * 60 + act_m) - (exp_h * 60 + exp_m))
    except Exception:
        return "fail_parse_local", actual_local, None
    if delta_min == 0:
        return "exact", actual_local, 0
    if delta_min <= 5:
        return "close_within_5min", actual_local, delta_min
    return "wrong_time", actual_local, delta_min


async def run_case(agent, case: dict, expected_local: str, tz: str) -> dict[str, Any]:
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input
    ts = str(case.get("metadata", {}).get("timestamp") or "")
    context = build_context(case.get("input", ""), ts, tz)
    prompt = build_reminder_intent_input(case.get("input", ""), context)
    started = datetime.now()
    error = None
    decision = None
    try:
        response = await asyncio.wait_for(agent.arun(input=prompt), timeout=120)
        decision = decision_from_response(response)
    except asyncio.TimeoutError:
        error = "timeout_120s"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = (datetime.now() - started).total_seconds()
    grade, actual_local, delta = grade_time(decision, expected_local, tz)
    return {
        "elapsed_seconds": round(elapsed, 2),
        "error": error,
        "grade": grade,
        "expected_local": expected_local,
        "actual_local": actual_local,
        "delta_minutes": delta,
        "decision_action": (
            str(decision.get("action")) if decision and isinstance(decision, dict) else None
        ),
        "trigger_at": (
            str(decision.get("trigger_at"))
            if decision and isinstance(decision, dict) and decision.get("trigger_at")
            else None
        ),
    }


async def main_async() -> int:
    cases, expectations = load_cases_and_expectations()
    selected = select_time_cases(expectations, TARGET_COUNT)
    print(f"Selected {len(selected)} cases with expected_creates.local_time")
    agent = build_agent(CANDIDATE)
    rows: list[dict[str, Any]] = []
    for n, idx in enumerate(selected, start=1):
        case = cases[idx]
        expected_local = expectations[idx]["expected_creates"][0]["local_time"]
        result = await run_case(agent, case, expected_local, TIMEZONE)
        rows.append({
            "case_index": idx,
            "input": case.get("input", "")[:80],
            "current_time": case.get("metadata", {}).get("timestamp"),
            **result,
        })
        marker = {
            "exact": "OK ",
            "close_within_5min": "~  ",
        }.get(result["grade"], "X  ")
        print(
            f"  [{n:2d}/{len(selected)}] case={idx:4d} {marker} "
            f"expected={expected_local} actual={result['actual_local']} "
            f"delta={result['delta_minutes']}min "
            f"({result['elapsed_seconds']}s)"
        )
    # Summarize
    grades: dict[str, int] = {}
    for r in rows:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1
    summary = {
        "total": len(rows),
        "exact": grades.get("exact", 0),
        "close_within_5min": grades.get("close_within_5min", 0),
        "wrong_time": grades.get("wrong_time", 0),
        "fail_other": sum(
            v for k, v in grades.items()
            if k not in {"exact", "close_within_5min", "wrong_time"}
        ),
        "grades_breakdown": grades,
    }
    summary["exact_rate"] = (
        round(summary["exact"] / summary["total"], 3) if summary["total"] else 0
    )
    summary["exact_or_close_rate"] = (
        round((summary["exact"] + summary["close_within_5min"]) / summary["total"], 3)
        if summary["total"]
        else 0
    )
    print(f"\n=== Phase 0 summary ===")
    print(f"  total: {summary['total']}")
    print(f"  exact: {summary['exact']} ({summary['exact_rate']*100:.1f}%)")
    print(f"  close (<=5min): {summary['close_within_5min']}")
    print(f"  exact or close: {summary['exact_or_close_rate']*100:.1f}%")
    print(f"  wrong_time: {summary['wrong_time']}")
    print(f"  fail_other: {summary['fail_other']}")
    print(f"  breakdown: {summary['grades_breakdown']}")
    payload = {
        "candidate": CANDIDATE,
        "timezone": TIMEZONE,
        "selected_indices": selected,
        "summary": summary,
        "rows": rows,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
