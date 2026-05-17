from pathlib import Path

from scripts.eval_reminder_tool_calls import load_cases, select_cases


def test_load_cases_preserves_corpus_shape_without_case_specific_assertions():
    path = Path("scripts/reminder_test_cases.json")
    cases = load_cases(path)

    assert cases
    assert all(isinstance(case.input, str) and case.input for case in cases)
    assert all(isinstance(case.expected_intent, str) for case in cases)
    assert all(isinstance(case.matched_keywords, list) for case in cases)
    assert all(isinstance(case.metadata, dict) for case in cases)


def test_select_cases_returns_the_requested_slice_without_case_specific_assertions():
    cases = load_cases(Path("scripts/reminder_test_cases.json"))

    selected = select_cases(cases, offset=2, limit=3)

    assert selected == cases[2:5]
