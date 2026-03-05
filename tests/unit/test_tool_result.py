import pytest


def test_append_first_result():
    """First call creates the list."""
    from agent.agno_agent.tools.tool_result import append_tool_result

    state = {}
    append_tool_result(state, tool_name="时区更新", ok=True, result_summary="已更新为纽约时间")
    assert state["tool_results"] == [
        {"tool_name": "时区更新", "ok": True, "result_summary": "已更新为纽约时间", "extra_notes": ""}
    ]


def test_append_second_result():
    """Second call appends, not overwrites."""
    from agent.agno_agent.tools.tool_result import append_tool_result

    state = {}
    append_tool_result(state, tool_name="A", ok=True, result_summary="ok")
    append_tool_result(state, tool_name="B", ok=False, result_summary="fail", extra_notes="hint")
    assert len(state["tool_results"]) == 2
    assert state["tool_results"][1]["extra_notes"] == "hint"


def test_extra_notes_defaults_to_empty():
    from agent.agno_agent.tools.tool_result import append_tool_result

    state = {}
    append_tool_result(state, tool_name="X", ok=True, result_summary="done")
    assert state["tool_results"][0]["extra_notes"] == ""
