from pathlib import Path

from scripts.eval_reminder_tool_calls import load_cases, select_cases


def test_loads_real_reminder_user_input_corpus():
    cases = load_cases(Path("scripts/reminder_test_cases.json"))

    assert len(cases) == 1892
    assert cases[0].input == "今天有这么两个事情提醒我 一个是17：57喝水，一个是每天17：58锻炼 "
    assert cases[0].expected_intent == "reminder"


def test_select_cases_supports_deterministic_offset_and_limit():
    cases = load_cases(Path("scripts/reminder_test_cases.json"))

    selected = select_cases(cases, offset=2, limit=3)

    assert [case.input for case in selected] == [
        "你可以没太难18:00 提醒我学英语么",
        "哦对还有，今天18:02提醒我喝水，每天18:04提醒我吃饭呢",
        "18:05提醒我出门",
    ]
