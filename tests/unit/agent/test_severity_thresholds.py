"""Verify the reminder corpus severity scheme and gate metadata."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
EXP = ROOT / "scripts/reminder_normal_path_expectations.json"


def test_every_case_has_severity():
    data = json.loads(EXP.read_text(encoding="utf-8"))
    missing = [
        idx
        for idx, case in data["cases"].items()
        if case.get("severity") not in {"critical", "important", "nice"}
    ]
    assert not missing, f"cases without severity: {missing[:10]}..."


def test_severity_distribution_is_roughly_balanced():
    data = json.loads(EXP.read_text(encoding="utf-8"))
    counts = {"critical": 0, "important": 0, "nice": 0}
    for case in data["cases"].values():
        counts[case["severity"]] += 1
    assert all(n >= 10 for n in counts.values()), (
        f"each tier should have >=10 cases: {counts}"
    )


def test_severity_standard_doc_exists():
    standard = ROOT / "docs/design-docs/reminder-corpus-severity.md"
    assert standard.exists()
    text = standard.read_text(encoding="utf-8")
    assert "100% pass" in text
    assert ">=95% pass" in text
    assert ">=80% pass" in text


def test_summarize_reports_severity_threshold_violations():
    from scripts.user_path_normal_eval import ReminderNormalPathResult, summarize

    data = json.loads(EXP.read_text(encoding="utf-8"))
    by_severity = {"critical": None, "important": None, "nice": None}
    for idx, case in data["cases"].items():
        severity = case.get("severity")
        if severity in by_severity and by_severity[severity] is None:
            by_severity[severity] = int(idx)
    assert all(index is not None for index in by_severity.values())

    def result(index: int, passed: bool) -> ReminderNormalPathResult:
        return ReminderNormalPathResult(
            index=index,
            input="",
            user_id="",
            original_from_user="",
            input_message_id="",
            input_status="processed",
            passed=passed,
            errors=[] if passed else ["synthetic_failure"],
            outputs=[],
            reminders=[],
            elapsed_seconds=0.0,
        )

    summary = summarize(
        [
            result(by_severity["critical"], passed=False),
            result(by_severity["important"], passed=True),
            result(by_severity["nice"], passed=True),
        ]
    )

    assert summary["per_severity"]["critical"]["pass_rate"] == 0.0
    assert summary["severity_violations"] == ["critical: 0.0% < 100%"]
