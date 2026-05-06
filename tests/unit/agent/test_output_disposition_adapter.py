from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    VisibleMessage,
)


def test_output_disposition_records_output_references():
    from agent.agno_agent.adapters.output_disposition import with_output_references

    result = AgentRunResult(
        visible_messages=[VisibleMessage(message_type="text", content="hello")],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={"runtime": "team"},
        output_disposition=OutputDisposition(status="ok"),
    )

    updated = with_output_references(result, ["out-1"])

    assert updated.output_disposition.status == "ok"
    assert updated.output_disposition.output_references == ("out-1",)
