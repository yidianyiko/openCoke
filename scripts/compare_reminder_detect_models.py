#!/usr/bin/env python3
"""Compare 3 reminder_detect model candidates on a curated case subset.

Bypasses Mongo / worker / message routing — directly invokes the LLM with
the same prompt the worker would, captures decision + latency, and grades
against the corpus expectations.

Usage:
    .venv/bin/python scripts/compare_reminder_detect_models.py \\
        --subset artifacts/evidence/reminder-model-compare/2026-05-12-subset.json \\
        --output artifacts/evidence/reminder-model-compare/2026-05-12-results.json
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agno.agent import Agent  # noqa: E402

from agent.agno_agent.model_factory import create_llm_model  # noqa: E402
from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input  # noqa: E402
from agent.agno_agent.runtime.context import (  # noqa: E402
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision  # noqa: E402
from agent.prompt.agent_instructions_prompt import (  # noqa: E402
    DESCRIPTION_REMINDER_DETECT,
    INSTRUCTIONS_REMINDER_DETECT,
)
from conf.config import CONF  # noqa: E402


CASES_PATH = PROJECT_ROOT / "scripts/reminder_test_cases.json"
EXPECTATIONS_PATH = PROJECT_ROOT / "scripts/reminder_normal_path_expectations.json"

CANDIDATES = [
    {
        "label": "deepseek-v4-flash-think-high",
        "config": {
            "provider": "siliconflow",
            "model_id": "deepseek-ai/DeepSeek-V4-Flash",
            "api_key": "${SiliconFlow_API_KEY}",
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
            "extra_body": {"thinking_budget": 4096},
        },
    },
    {
        "label": "kimi-k2.6",
        "config": {
            "provider": "siliconflow",
            "model_id": "Pro/moonshotai/Kimi-K2.6",
            "api_key": "${SiliconFlow_API_KEY}",
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
        },
    },
]


def resolve_env_placeholders(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    if isinstance(value, dict):
        return {k: resolve_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_placeholders(v) for v in value]
    return value


def load_subset(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases_and_expectations() -> tuple[list[dict], dict[int, dict]]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["test_cases"]
    expectations = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))["cases"]
    return cases, {int(k): v for k, v in expectations.items()}


def build_context(case_input: str, timestamp_str: str, timezone_name: str) -> AgentRunContext:
    try:
        parsed = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        current_time = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    except (ValueError, TypeError):
        current_time = datetime.now(ZoneInfo(timezone_name))
    user = TrustedUserContext(
        id="compare-user",
        nickname="ComparUser",
        timezone=timezone_name,
        metadata={},
    )
    character = TrustedCharacterContext(id="compare-character", nickname="Coke", metadata={})
    conversation = TrustedConversationContext(
        id="compare-conv",
        platform="business",
        route_key=None,
        metadata={},
    )
    relation = TrustedRelationContext(
        uid="compare-user", cid="compare-character", metadata={}
    )
    return AgentRunContext(
        user=user,
        character=character,
        conversation=conversation,
        relation=relation,
        platform="business",
        recent_chat_history="(empty)",
        current_time=current_time,
        runtime_metadata={},
    )


def build_agent(candidate: dict) -> Agent:
    """Build a fresh reminder_detect agent with the candidate's model config."""
    saved = copy.deepcopy(CONF["llm"]["roles"].get("reminder_detect"))
    CONF["llm"]["roles"]["reminder_detect"] = resolve_env_placeholders(candidate["config"])
    try:
        model = create_llm_model(max_tokens=8000, role="reminder_detect")
    finally:
        if saved is None:
            CONF["llm"]["roles"].pop("reminder_detect", None)
        else:
            CONF["llm"]["roles"]["reminder_detect"] = saved
    agent = Agent(
        id=f"compare-{candidate['label']}",
        name="ReminderDetectAgent",
        model=model,
        description=DESCRIPTION_REMINDER_DETECT,
        instructions=INSTRUCTIONS_REMINDER_DETECT,
        output_schema=ReminderDetectDecision,
        structured_outputs=True,
        markdown=False,
        num_history_messages=15,
        compress_tool_results=True,
        max_tool_calls_from_history=5,
    )
    return agent


def decision_from_response(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    if isinstance(response, ReminderDetectDecision):
        return response.model_dump(mode="json")
    content = getattr(response, "content", None)
    if isinstance(content, ReminderDetectDecision):
        return content.model_dump(mode="json")
    if isinstance(content, dict):
        try:
            return ReminderDetectDecision.model_validate(content).model_dump(mode="json")
        except Exception:
            return content
    if isinstance(content, str):
        text = content.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                return ReminderDetectDecision.model_validate_json(text).model_dump(mode="json")
            except Exception:
                try:
                    return json.loads(text)
                except Exception:
                    return {"_raw_text": text}
        return {"_raw_text": text}
    return {"_response_repr": repr(response)[:500]}


async def run_one_case(
    agent: Agent,
    case_input: str,
    timestamp_str: str,
    timezone_name: str,
) -> dict[str, Any]:
    context = build_context(case_input, timestamp_str, timezone_name)
    prompt = build_reminder_intent_input(case_input, context)
    started = time.perf_counter()
    error = None
    decision = None
    try:
        response = await asyncio.wait_for(agent.arun(input=prompt), timeout=180)
        decision = decision_from_response(response)
    except asyncio.TimeoutError:
        error = "timeout_180s"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    return {
        "elapsed_seconds": round(elapsed, 2),
        "error": error,
        "decision": decision,
    }


def grade(decision: dict[str, Any] | None, expected: str) -> str:
    if decision is None:
        return "fail_no_decision"
    intent = str(decision.get("intent_type") or "").strip().lower()
    if not intent:
        return "fail_no_intent"
    if intent == expected:
        return "pass"
    return f"fail_intent_{intent}_vs_{expected}"


def bucket_of(case_index: int, buckets: dict[str, list[int]]) -> str:
    for bucket, members in buckets.items():
        if case_index in members:
            return bucket
    return "unknown"


async def run_candidate(
    candidate: dict,
    selected: list[int],
    cases: list[dict],
    expectations: dict[int, dict],
    buckets: dict[str, list[int]],
    timezone_name: str,
) -> dict[str, Any]:
    print(f"[{candidate['label']}] building agent...", flush=True)
    agent = build_agent(candidate)
    rows: list[dict[str, Any]] = []
    for n, idx in enumerate(selected, start=1):
        case = cases[idx]
        expectation = expectations.get(idx, {})
        expected_intent = str(
            expectation.get("evaluation_expectation") or ""
        ).strip().lower()
        timestamp_str = str(case.get("metadata", {}).get("timestamp") or "")
        result = await run_one_case(
            agent,
            case.get("input", ""),
            timestamp_str,
            timezone_name,
        )
        grade_label = grade(result["decision"], expected_intent)
        rows.append({
            "case_index": idx,
            "bucket": bucket_of(idx, buckets),
            "expected": expected_intent,
            "input": case.get("input", "")[:120],
            "elapsed_seconds": result["elapsed_seconds"],
            "error": result["error"],
            "grade": grade_label,
            "decision_intent": (
                str(result["decision"].get("intent_type")) if result["decision"] else None
            ),
            "decision_action": (
                str(result["decision"].get("action")) if result["decision"] else None
            ),
            "decision": result["decision"],
        })
        status = "OK" if grade_label == "pass" else "X "
        print(
            f"  [{n:3d}/{len(selected)}] case={idx:4d} bucket={rows[-1]['bucket']:28s} "
            f"{status} {grade_label} ({result['elapsed_seconds']}s)",
            flush=True,
        )
    pass_count = sum(1 for r in rows if r["grade"] == "pass")
    bucket_stats: dict[str, dict[str, int]] = {}
    for r in rows:
        b = r["bucket"]
        if b not in bucket_stats:
            bucket_stats[b] = {"total": 0, "pass": 0}
        bucket_stats[b]["total"] += 1
        if r["grade"] == "pass":
            bucket_stats[b]["pass"] += 1
    elapsed_values = [r["elapsed_seconds"] for r in rows if r["error"] is None]
    return {
        "label": candidate["label"],
        "config": candidate["config"],
        "summary": {
            "total": len(rows),
            "pass": pass_count,
            "pass_rate": round(pass_count / len(rows), 3) if rows else 0,
            "mean_elapsed_s": round(sum(elapsed_values) / len(elapsed_values), 2)
            if elapsed_values
            else None,
            "errors": sum(1 for r in rows if r["error"]),
        },
        "buckets": bucket_stats,
        "rows": rows,
    }


async def main_async(args: argparse.Namespace) -> int:
    subset = load_subset(args.subset)
    cases, expectations = load_cases_and_expectations()
    selected: list[int] = subset["selected_indices"]
    buckets: dict[str, list[int]] = subset["buckets"]
    print(
        f"Cases: {len(selected)} | candidates: {len(CANDIDATES)} | "
        f"timezone={args.timezone}",
        flush=True,
    )
    results: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        result = await run_candidate(
            candidate,
            selected,
            cases,
            expectations,
            buckets,
            args.timezone,
        )
        results.append(result)
        print(
            f"[{candidate['label']}] pass {result['summary']['pass']}/"
            f"{result['summary']['total']} "
            f"({result['summary']['pass_rate'] * 100:.1f}%) "
            f"mean_latency={result['summary']['mean_elapsed_s']}s",
            flush=True,
        )
    payload = {
        "subset_path": str(args.subset),
        "timezone": args.timezone,
        "selected_indices": selected,
        "candidates": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote results to: {args.output}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subset",
        type=Path,
        default=PROJECT_ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-subset.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-results.json",
    )
    parser.add_argument("--timezone", default="Asia/Tokyo")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print(f"fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
