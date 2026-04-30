#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_EXPECTATIONS_PATH = Path("scripts/reminder_normal_path_expectations.json")
DEFAULT_PROMPT_PATHS = (
    Path("agent/prompt/agent_instructions_prompt.py"),
    Path("agent/prompt/chat_contextprompt.py"),
)
DEFAULT_WORKFLOW_PATH = Path("agent/agno_agent/workflows/prepare_workflow.py")


def load_expectation_cases(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases", data)
    return {str(index): dict(value) for index, value in raw_cases.items()}


def count_negative_constraints(text: str) -> int:
    return len(
        re.findall(
            r"\b(?:Avoid|avoid|Do not|do not|Never|never)\b|不要|禁止",
            text,
        )
    )


def build_report(
    *,
    expectations_path: Path = DEFAULT_EXPECTATIONS_PATH,
    prompt_paths: tuple[Path, ...] = DEFAULT_PROMPT_PATHS,
    workflow_path: Path = DEFAULT_WORKFLOW_PATH,
) -> dict[str, Any]:
    cases = load_expectation_cases(expectations_path)
    expectation_counts = Counter(
        str(case.get("evaluation_expectation") or "crud") for case in cases.values()
    )
    variant_cases = [
        index
        for index, case in cases.items()
        if any(
            create.get("title_variants")
            for create in case.get("expected_creates") or []
        )
    ]
    variant_count = sum(
        len(create.get("title_variants") or [])
        for case in cases.values()
        for create in case.get("expected_creates") or []
    )
    prompt_metrics = {}
    for path in prompt_paths:
        text = path.read_text(encoding="utf-8")
        prompt_metrics[str(path)] = {
            "non_empty_lines": sum(1 for line in text.splitlines() if line.strip()),
            "negative_constraints": count_negative_constraints(text),
        }

    workflow_text = workflow_path.read_text(encoding="utf-8")
    return {
        "fixture_overrides": len(cases),
        "evaluation_expectation_counts": dict(sorted(expectation_counts.items())),
        "title_variant_cases": variant_cases,
        "title_variants": variant_count,
        "prompt_metrics": prompt_metrics,
        "workflow_regex_fast_path_markers": {
            "looks_like_reminder": "_looks_like_reminder" in workflow_text,
            "actionable_patterns": "_ACTIONABLE_" in workflow_text,
            "explicit_reminder_patterns": "_EXPLICIT_REMINDER" in workflow_text,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report reminder-detect drift metrics."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
