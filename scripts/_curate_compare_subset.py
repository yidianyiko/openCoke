"""Deterministic curation of a ~40-case subset from reminder expectations.

Picks representatives across the guard categories that recent commits have
touched. Output: stdout JSON with bucket -> [case_index, ...] and a flat
sorted list of selected indices.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXP_PATH = ROOT / "scripts/reminder_normal_path_expectations.json"
CASES_PATH = ROOT / "scripts/reminder_test_cases.json"


def load() -> tuple[dict, list]:
    exp = json.loads(EXP_PATH.read_text(encoding="utf-8"))["cases"]
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["test_cases"]
    return exp, cases


def text_for(idx: int, exp: dict, cases: list) -> tuple[str, str, str]:
    e = exp[str(idx)]
    inp = cases[idx].get("input", "") if idx < len(cases) else ""
    reason = e.get("evaluation_reason", "")
    return inp, reason, e.get("evaluation_expectation", "")


def matches(idx: int, pat: re.Pattern, exp: dict, cases: list) -> bool:
    inp, reason, _ = text_for(idx, exp, cases)
    return bool(pat.search(inp) or pat.search(reason))


RULES = [
    # (bucket, target_count, regex)
    ("chinese_clock_nightly",   3, re.compile(r"晚上|夜里|nightly|evening|凌晨|傍晚|半夜")),
    ("chinese_clock_past_X",    3, re.compile(r"点过|past[- ]?\w*?five|past.*\d.*minutes|点零?\d|preserve.*minute")),
    ("chinese_clock_before_X",  2, re.compile(r"差.*分|before-hour|before.*hour")),
    ("relative_delay",          5, re.compile(r"分钟后|小时后|min later|in \d|timer|pomodoro|过.\d|after \d.*min|relative[- ]delay")),
    ("bare_clock",              4, re.compile(r"bare[- ]clock|same afternoon|past one[- ]shot|next future|undesignated")),
    ("batch_multi",             3, re.compile(r"batch|multi[- ]create|multiple reminders|两个.*提醒|several reminders")),
    ("weekly_recurrence",       3, re.compile(r"weekday|周一|周二|周三|周四|周五|周六|周日|每周|每星期|listed weekdays")),
    ("monthly_or_dayofmonth",   2, re.compile(r"day of month|每月|号.*提醒|day-of-month|月号|monthly")),
    ("bounded_window",          3, re.compile(r"bounded|deadline|until|直到|到.*点|窗口|窗内")),
    ("clarify_date_only",       3, re.compile(r"date[- ]only|no clock|no time|missing time|没有具体时间")),
    ("clarify_completion",      2, re.compile(r"completion[- ]?cond|after I finish|finish|读完|看完|完成后")),
    ("clarify_status_only",     2, re.compile(r"status[- ]only|referential|这件事|还没做|that thing")),
    ("clarify_ambiguous_time",  2, re.compile(r"ambiguous|time range|range.*incomplete|incomplete time|不明确")),
    ("discussion_meta",         2, re.compile(r"meta|discussion|behavior.*reminder|feature work|opt[- ]out|测一测")),
    ("discussion_intent",       1, re.compile(r"need to|intention|plan to|想.*提醒|准备.*提醒|想做|计划")),
]


def main() -> None:
    exp, cases = load()
    indices = sorted(int(k) for k in exp)
    used: set[int] = set()
    buckets: dict[str, list[int]] = {}
    for bucket, target, pat in RULES:
        picks: list[int] = []
        for idx in indices:
            if idx in used:
                continue
            if matches(idx, pat, exp, cases):
                picks.append(idx)
                if len(picks) >= target:
                    break
        used.update(picks)
        buckets[bucket] = picks
    # Add a few straightforward crud baselines (no special features)
    baseline_pat = re.compile(r"")
    plain_picks: list[int] = []
    for idx in indices:
        if idx in used:
            continue
        _, reason, expect = text_for(idx, exp, cases)
        if expect != "crud":
            continue
        # very short reasons = simpler cases
        if len(reason) < 90 and "Explicit" in reason and "concrete" in reason:
            plain_picks.append(idx)
            if len(plain_picks) >= 2:
                break
    used.update(plain_picks)
    buckets["plain_crud_baseline"] = plain_picks

    summary = {
        "buckets": {k: v for k, v in buckets.items()},
        "selected_indices": sorted(used),
        "total": len(used),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
