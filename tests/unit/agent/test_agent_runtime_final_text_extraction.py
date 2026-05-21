from agent.agno_agent.runtime.agent_runtime import _string_content


def test_string_content_returns_stripped_run_response_content():
    assert _string_content("  final answer  ") == "final answer"


def test_string_content_rejects_non_string_run_response_content():
    assert _string_content({"role": "assistant", "content": "ignored"}) == ""
