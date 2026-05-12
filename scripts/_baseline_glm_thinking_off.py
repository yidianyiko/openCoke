"""Run GLM-5.1 thinking-OFF (current production setting) on the same 20-case subset.

Fills the missing baseline in the comparison.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_reminder_detect_models import (  # noqa: E402
    build_agent,
    load_cases_and_expectations,
    load_subset,
    run_candidate,
)


GLM_BASELINE = {
    "label": "glm-5.1-thinking-off-baseline",
    "config": {
        "provider": "siliconflow",
        "model_id": "Pro/zai-org/GLM-5.1",
        "api_key": "${SiliconFlow_API_KEY}",
        "base_url": "https://api.siliconflow.cn/v1",
        "max_retries": 2,
        "extra_body": {"enable_thinking": False},
    },
}


async def main_async() -> int:
    subset_path = PROJECT_ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-subset-20.json"
    output_path = PROJECT_ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-baseline-glm-thinking-off.json"
    subset = load_subset(subset_path)
    cases, expectations = load_cases_and_expectations()
    print(
        f"Baseline run: {GLM_BASELINE['label']} on {len(subset['selected_indices'])} cases",
        flush=True,
    )
    result = await run_candidate(
        GLM_BASELINE,
        subset["selected_indices"],
        cases,
        expectations,
        subset["buckets"],
        "Asia/Tokyo",
    )
    print(
        f"\n[{result['label']}] pass {result['summary']['pass']}/{result['summary']['total']} "
        f"({result['summary']['pass_rate'] * 100:.1f}%) mean_latency={result['summary']['mean_elapsed_s']}s",
        flush=True,
    )
    output_path.write_text(
        json.dumps(
            {"subset_path": str(subset_path), "timezone": "Asia/Tokyo", "candidates": [result]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote: {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
