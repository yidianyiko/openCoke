"""Bulk-label reminder corpus cases with severity tiers.

Heuristic labels are based on expectation metadata and case text. Run once,
review the JSON, and adjust by hand. This is not runtime code.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "scripts/reminder_normal_path_expectations.json"
CASES_PATH = ROOT / "scripts/reminder_test_cases.json"

CRITICAL_PATTERNS = [
    re.compile(r"12[- ]?hour|am/pm|next[_. ]morning|same[_. ]afternoon", re.I),
    re.compile(r"dropped|missing|partial[_. ]execut|multi-create", re.I),
    re.compile(r"delete.*create|cancel.*create|cancel|delete", re.I),
    re.compile(r"without.*content|no reminder content|generic reminder", re.I),
]

NICE_PATTERNS = [
    re.compile(r"chinese.*period|period-of-day|specific.*phrasing", re.I),
    re.compile(r"noisy|casual|suffix|particle|filler|relative-time", re.I),
    re.compile(r"stale|fixture|redundant|reorder|merge", re.I),
]


def classify(reason: str, expectation: str, case_input: str) -> str:
    text = f"{reason}\n{case_input}".lower()
    if expectation in {"discussion", "query"}:
        return "nice"
    if expectation in {"delete", "cancel", "update"}:
        return "critical"
    for pattern in CRITICAL_PATTERNS:
        if pattern.search(text):
            return "critical"
    for pattern in NICE_PATTERNS:
        if pattern.search(text):
            return "nice"
    if expectation == "clarify":
        return "important"
    return "important"


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    corpus = json.loads(CASES_PATH.read_text(encoding="utf-8"))["test_cases"]
    stats = {"critical": 0, "important": 0, "nice": 0}
    for idx, case in cases.items():
        if case.get("severity") in stats:
            stats[case["severity"]] += 1
            continue
        case_index = int(idx)
        expectation = str(case.get("evaluation_expectation") or "").strip().lower()
        reason = str(case.get("evaluation_reason") or "")
        case_input = str(corpus[case_index].get("input") or "") if case_index < len(corpus) else ""
        severity = classify(reason, expectation, case_input)
        case["severity"] = severity
        stats[severity] += 1
    PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Labeled. Total: {sum(stats.values())} | {stats}")
    print("Review critical and nice labels before committing.")


if __name__ == "__main__":
    main()
