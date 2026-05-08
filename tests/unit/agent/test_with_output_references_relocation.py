from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    with_output_references,
)


def test_with_output_references_attaches_references():
    base = AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        tool_results=(),
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status="ok"),
    )

    updated = with_output_references(base, ("ref-1",))

    assert updated.output_disposition.output_references == ("ref-1",)
    assert updated.output_disposition.status == "ok"
