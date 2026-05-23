"""Phase 0 v2: streamlined prompt + explicit AM/PM rule, same 30 cases.

Hypothesis: aggressive prompt slimming + explicit time-disambiguation rule
will raise exact-match rate above the 63.3 % baseline AND reduce the 23 %
timeout rate, without any Python time helpers.

Compare results to artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy.json
"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agno.agent import Agent  # noqa: E402

from agent.agno_agent.model_factory import create_llm_model  # noqa: E402
from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision  # noqa: E402
from conf.config import CONF  # noqa: E402
from scripts.compare_reminder_detect_models import (  # noqa: E402
    build_context,
    decision_from_response,
    resolve_env_placeholders,
)
from scripts._phase0_time_accuracy import (  # noqa: E402
    CANDIDATE,
    TIMEZONE,
    grade_time,
    load_cases_and_expectations,
    select_time_cases,
)


# ============================================================
# Streamlined v2 prompt — focus on intent + ISO output.
# ~600 tokens vs original ~3000.
# ============================================================
V2_DESCRIPTION = "Reminder intent detector. Output a structured ReminderDetectDecision."

V2_INSTRUCTIONS = """<instructions>
You analyze the user message and output a structured ReminderDetectDecision.

## Intent

- **crud**: user asks to be reminded/notified/woken/called/checked-on at a concrete time or cadence. Pomodoro = 25 min from current_time. Set action to create/update/delete/complete/batch.
- **clarify**: reminder intent is clear but title or time is missing/ambiguous.
- **query**: user asks to view existing reminders. action="list".
- **discussion**: ordinary plans, intentions, schedules, complaints about reminder behavior. No action.

## Time output (CRITICAL)

`trigger_at` is timezone-aware ISO 8601 in the user's timezone.

When the user gives a bare clock (e.g. "7点", "10:30", "晚上九点"):

1. **Resolve to a specific local datetime using current_time**:
   - If a Chinese period marker is given (早上/上午/中午/下午/晚上/凌晨), use it: 早上/上午 = AM, 下午/晚上 = PM, 凌晨 = 00:00-05:00, 中午 = 12:00.
   - If no period marker AND the bare hour < current_hour, **prefer PM same day** (add 12h) when the PM interpretation is within 12 hours of current_time. Example: at 16:34, "七点" → 19:00 same day, not 07:00 next day.
   - If no period marker AND the bare hour > current_hour, use it as-is on current date.
   - If bare hour equals current_hour, use the next occurrence (today PM or tomorrow AM).

2. **Relative delays** ("after X min", "过 X 分钟", "20分钟后"): add to current_time.

3. **Multi-clock inputs** ("1 点睡觉，明天 6 点半叫我起床"): the trigger_at is the **reminder time**, not the bedtime. Use the clock attached to the reminder verb (叫/提醒/醒).

4. **Bounded recurring cadence with end**: deadline_at = end time. trigger_at = first occurrence.

## Other rules

- Date-only ("明天提醒我") clarifies for time. Never invent default times.
- Time-only with no title clarifies, except bare wake/call where the verb is the title.
- Status-only fragments ("还没做", "这件事") clarify for content.
- Completion-conditioned ("读完后提醒我") clarifies for when.
- For batch action, every operation uses {action, title, trigger_at, ...}; include top-level schedule_basis ("one_shot" / "explicit_occurrences" / "explicit_cadence") and schedule_evidence (the user wording).
- For weekly recurrence with listed weekdays, BYDAY includes all of them.
- Update/delete/complete need a clear keyword target; otherwise clarify.
- Exclude trailing modal particles from titles. Preserve quoted text.
- Clarification language matches user message language.

## Schema

- Use intent_type and action separately.
- action ∈ {"", create, update, delete, complete, batch, list}.
- Single reminder uses top-level title/trigger_at; multiple use action="batch" + operations.
- Output only the structured decision; no chat text.
</instructions>"""


def v2_build_reminder_intent_input(input_message: str, run_context) -> str:
    """Streamlined input builder — drops the 25 inline rules."""
    return "\n".join([
        "### Current time",
        run_context.current_time.isoformat(),
        "",
        "### User timezone",
        run_context.user.timezone or "UTC",
        "",
        "### Recent conversation (last 5)",
        run_context.recent_chat_history or "(empty)",
        "",
        "### Current user message",
        input_message,
    ])


def build_v2_agent() -> Agent:
    saved = copy.deepcopy(CONF["llm"]["roles"].get("reminder_detect"))
    CONF["llm"]["roles"]["reminder_detect"] = resolve_env_placeholders(CANDIDATE["config"])
    try:
        model = create_llm_model(max_tokens=8000, role="reminder_detect")
    finally:
        if saved is None:
            CONF["llm"]["roles"].pop("reminder_detect", None)
        else:
            CONF["llm"]["roles"]["reminder_detect"] = saved
    return Agent(
        id="compare-v2",
        name="ReminderDetectAgentV2",
        model=model,
        description=V2_DESCRIPTION,
        instructions=V2_INSTRUCTIONS,
        output_schema=ReminderDetectDecision,
        structured_outputs=True,
        markdown=False,
        num_history_messages=15,
        compress_tool_results=True,
        max_tool_calls_from_history=5,
    )


async def run_case(agent, case, expected_local, tz):
    from datetime import datetime
    context = build_context(case.get("input", ""), str(case.get("metadata", {}).get("timestamp") or ""), tz)
    prompt = v2_build_reminder_intent_input(case.get("input", ""), context)
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
        "trigger_at": (
            str(decision.get("trigger_at"))
            if decision and isinstance(decision, dict) and decision.get("trigger_at")
            else None
        ),
    }


async def main_async() -> int:
    cases, expectations = load_cases_and_expectations()
    selected = select_time_cases(expectations, 30)
    print(f"Phase 0 v2: streamlined prompt on {len(selected)} cases")
    agent = build_v2_agent()
    rows = []
    for n, idx in enumerate(selected, start=1):
        case = cases[idx]
        expected_local = expectations[idx]["expected_creates"][0]["local_time"]
        result = await run_case(agent, case, expected_local, TIMEZONE)
        rows.append({"case_index": idx, "input": case.get("input", "")[:80],
                     "current_time": case.get("metadata", {}).get("timestamp"), **result})
        marker = {"exact": "OK ", "close_within_5min": "~  "}.get(result["grade"], "X  ")
        print(
            f"  [{n:2d}/{len(selected)}] case={idx:4d} {marker} "
            f"exp={expected_local} act={result['actual_local']} "
            f"d={result['delta_minutes']}min ({result['elapsed_seconds']}s)"
        )
    grades: dict[str, int] = {}
    for r in rows:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1
    summary = {
        "total": len(rows),
        "exact": grades.get("exact", 0),
        "close_within_5min": grades.get("close_within_5min", 0),
        "wrong_time": grades.get("wrong_time", 0),
        "fail_other": sum(v for k, v in grades.items()
                          if k not in {"exact", "close_within_5min", "wrong_time"}),
        "grades_breakdown": grades,
    }
    summary["exact_rate"] = round(summary["exact"] / summary["total"], 3) if summary["total"] else 0
    summary["exact_or_close_rate"] = round(
        (summary["exact"] + summary["close_within_5min"]) / summary["total"], 3
    ) if summary["total"] else 0
    print(f"\n=== Phase 0 v2 summary ===")
    print(f"  total: {summary['total']}")
    print(f"  exact: {summary['exact']} ({summary['exact_rate']*100:.1f}%)")
    print(f"  close: {summary['close_within_5min']}")
    print(f"  exact or close: {summary['exact_or_close_rate']*100:.1f}%")
    print(f"  wrong_time: {summary['wrong_time']}")
    print(f"  fail_other: {summary['fail_other']}")
    print(f"  breakdown: {summary['grades_breakdown']}")
    output_path = PROJECT_ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-phase0-v2-streamlined-prompt.json"
    output_path.write_text(json.dumps({"summary": summary, "rows": rows},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
