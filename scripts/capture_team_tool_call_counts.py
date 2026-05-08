#!/usr/bin/env python3
"""Capture Team-runtime tool-call counts for native-tool parity checks.

This is a one-shot staging helper. It issues real LLM calls through the current
Team runtime and writes the baseline consumed by
tests/eval/test_tool_call_count_parity.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

from agent.agno_agent.runtime.team_runtime import run_team_runtime
from tests.eval.test_tool_call_count_parity import SCENARIOS

OUTPUT = Path(
    "artifacts/evidence/2026-05-09-pre-cutover-baseline/team-tool-call-counts.json"
)


async def _run_one(scenario_name: str) -> int:
    case = SCENARIOS[scenario_name]
    legacy_context = {
        "user": {
            "id": "parity-u",
            "nickname": "Parity",
            "timezone": case.get("timezone", "Asia/Tokyo"),
        },
        "character": {"id": "parity-c", "name": "Coke"},
        "conversation": {"id": f"parity-{scenario_name}", "platform": "business"},
        "relation": {"uid": "parity-u", "cid": "parity-c"},
        "platform": "business",
    }
    result = await run_team_runtime(
        context=legacy_context,
        input_message_str=case["input_text"],
        message_source="user",
        metadata={},
        current_time=datetime.now(UTC),
    )
    return int(result.metrics.get("capability_result_count", 0))


async def _main() -> None:
    if os.environ.get("AGENT_RUNTIME_REAL_MODEL_SMOKE") != "1":
        raise SystemExit(
            "Refusing to issue real LLM calls without AGENT_RUNTIME_REAL_MODEL_SMOKE=1"
        )

    counts = {}
    for name in SCENARIOS:
        counts[name] = await _run_one(name)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(_main())
