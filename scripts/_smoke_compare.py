"""6-call smoke test: 3 candidates x 2 cases. Exits non-zero on any failure."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_reminder_detect_models import (  # noqa: E402
    CANDIDATES,
    build_agent,
    load_cases_and_expectations,
    run_one_case,
)

SAMPLE_INDICES = [0, 7]  # one CRUD chinese + one English relative-delay


async def main_async() -> int:
    cases, expectations = load_cases_and_expectations()
    print(f"smoke: {len(CANDIDATES)} candidates x {len(SAMPLE_INDICES)} cases")
    failed = 0
    for candidate in CANDIDATES:
        print(f"\n--- {candidate['label']} ({candidate['config']['model_id']}) ---")
        agent = build_agent(candidate)
        for idx in SAMPLE_INDICES:
            case = cases[idx]
            ts = str(case.get("metadata", {}).get("timestamp") or "")
            result = await run_one_case(agent, case.get("input", ""), ts, "Asia/Tokyo")
            status = "ERR" if result["error"] else "OK"
            intent = (
                result["decision"].get("intent_type")
                if result["decision"] and isinstance(result["decision"], dict)
                else None
            )
            print(
                f"  case {idx}: {status} latency={result['elapsed_seconds']}s "
                f"intent={intent} error={result['error']}"
            )
            if result["error"]:
                failed += 1
    print(f"\nsmoke summary: failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
