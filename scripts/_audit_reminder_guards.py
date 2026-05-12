"""Measure which reminder_intent guard helpers match corpus inputs.

This is a candidate-finding tool, not proof that a guard is dead. A zero hit
means "review this helper and its call site"; tests and runtime context may
still cover behavior the corpus sample does not exercise.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.agno_agent.capabilities.reminder_intent as rim
from scripts._phase0_time_accuracy import load_cases_and_expectations

GUARD_PREFIXES = (
    "_should_retry_for_",
    "_should_clarify_",
    "_drop_",
    "_input_is_",
    "_input_has_",
    "_normalize_",
    "_should_treat_",
    "_is_today_time_range_",
    "_is_bounded_cadence_",
    "_is_unbounded_high_frequency_",
)

OUTPUT_PATH = Path(
    "artifacts/evidence/reminder-model-compare/2026-05-12-guard-coverage.json"
)


def discover_guards() -> list[tuple[str, Any, inspect.Signature]]:
    out = []
    for name, fn in inspect.getmembers(rim, inspect.isfunction):
        if not any(name.startswith(prefix) for prefix in GUARD_PREFIXES):
            continue
        out.append((name, fn, inspect.signature(fn)))
    return sorted(out)


def generic_decision() -> SimpleNamespace:
    return SimpleNamespace(
        intent_type="crud",
        action="create",
        title="placeholder",
        trigger_at="2026-05-12T10:00:00+09:00",
        operations=[],
        rrule="",
        schedule_basis="",
        schedule_evidence="",
        deadline_at="",
        new_title="",
        new_trigger_at="",
        keyword="",
        reminder_id="",
    )


def call_safely(fn: Any, sig: inspect.Signature, input_message: str) -> bool | None:
    params = list(sig.parameters)
    decision = generic_decision()
    try:
        if len(params) == 1:
            result = fn(input_message)
        elif len(params) == 2:
            result = fn(input_message, decision)
        else:
            return None
    except Exception:
        return None
    if isinstance(result, str):
        return result != input_message
    return bool(result)


def main() -> None:
    cases, expectations = load_cases_and_expectations()
    guards = discover_guards()
    rows = []
    for name, fn, sig in guards:
        hits = 0
        skipped = 0
        for idx in sorted(expectations):
            if idx >= len(cases):
                continue
            text = str(cases[idx].get("input") or "")
            result = call_safely(fn, sig, text)
            if result is None:
                skipped += 1
            elif result:
                hits += 1
        rows.append({"guard": name, "hits": hits, "skipped": skipped})
    rows.sort(key=lambda row: (row["hits"], row["guard"]))
    print(f"{'GUARD':56s} HITS  SKIPPED")
    for row in rows:
        print(f"  {row['guard']:54s} {row['hits']:>4d}  {row['skipped']:>4d}")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "total_cases": len(expectations),
                "rows": rows,
                "notes": [
                    "Zero hits are candidates for manual review, not automatic deletion.",
                    "Helpers with skipped > 0 need signature-specific instrumentation.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote: {OUTPUT_PATH}")
    print(f"Dead candidates (hits=0): {sum(1 for row in rows if row['hits'] == 0)}")
    print(
        f"Low-hit candidates (1-2): "
        f"{sum(1 for row in rows if 0 < row['hits'] <= 2)}"
    )
    print(f"Used candidates (>=3): {sum(1 for row in rows if row['hits'] >= 3)}")


if __name__ == "__main__":
    main()
