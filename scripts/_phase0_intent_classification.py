"""Phase 0 intent: measure GLM-5.1 thinking-off intent_type accuracy.

Complements _phase0_time_accuracy.py, which only grades trigger_at. This
grades whether the LLM's decision.intent_type matches the expectation's
evaluation_expectation across crud, clarify, discussion, and query.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._phase0_time_accuracy import CANDIDATE, TIMEZONE  # noqa: E402
from scripts.compare_reminder_detect_models import (  # noqa: E402
    build_agent,
    build_context,
    decision_from_response,
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts/evidence/reminder-model-compare/2026-05-12-phase0-intent-classification.json"
)


def select_intent_cases(
    expectations: dict[int, dict[str, Any]],
    target_per_class: int = 10,
) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = {
        "crud": [],
        "clarify": [],
        "discussion": [],
        "query": [],
    }
    for idx in sorted(expectations):
        expectation = expectations[idx]
        cls = str(expectation.get("evaluation_expectation") or "").strip().lower()
        if cls in buckets and len(buckets[cls]) < target_per_class:
            buckets[cls].append(idx)
    return buckets


def grade_intent(decision: dict[str, Any] | None, expected: str) -> str:
    if decision is None:
        return "fail_no_decision"
    got = str(decision.get("intent_type") or "").lower()
    if not got:
        return "fail_no_intent"
    return "pass" if got == expected else f"fail_got_{got}"


async def run_one(agent, case: dict[str, Any], expected_intent: str, tz: str) -> dict:
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
    return {
        "elapsed_seconds": round(elapsed, 2),
        "error": error,
        "grade": grade_intent(decision, expected_intent),
        "got_intent": decision.get("intent_type") if decision else None,
    }


async def main_async() -> int:
    from scripts._phase0_time_accuracy import load_cases_and_expectations

    cases, expectations = load_cases_and_expectations()
    buckets = select_intent_cases(expectations, target_per_class=10)
    selected = sorted({case_index for values in buckets.values() for case_index in values})
    print(f"Phase 0 intent: {len(selected)} cases across {len(buckets)} classes")
    agent = build_agent(CANDIDATE)
    rows = []
    for n, idx in enumerate(selected, start=1):
        case = cases[idx]
        expected = str(expectations[idx].get("evaluation_expectation") or "").lower()
        result = await run_one(agent, case, expected, TIMEZONE)
        rows.append(
            {
                "case_index": idx,
                "expected": expected,
                "input": case.get("input", "")[:80],
                **result,
            }
        )
        marker = "OK" if result["grade"] == "pass" else "X "
        print(
            f"  [{n:2d}/{len(selected)}] case={idx:4d} {marker} "
            f"exp={expected} got={result['got_intent']} "
            f"({result['elapsed_seconds']}s)"
        )
    passes = sum(1 for row in rows if row["grade"] == "pass")
    per_class = {cls: {"total": 0, "pass": 0} for cls in buckets}
    for row in rows:
        per_class[row["expected"]]["total"] += 1
        if row["grade"] == "pass":
            per_class[row["expected"]]["pass"] += 1
    print("\n=== Intent Phase 0 summary ===")
    print(f"  total: {len(rows)}, pass: {passes} ({passes / len(rows) * 100:.1f}%)")
    for cls, stats in per_class.items():
        rate = stats["pass"] / stats["total"] * 100 if stats["total"] else 0
        print(f"  {cls:12s}: {stats['pass']}/{stats['total']} ({rate:.1f}%)")
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "summary": {
                    "total": len(rows),
                    "pass": passes,
                    "per_class": per_class,
                },
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
