from agent.agno_agent.runtime.domain_results import (
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    VisibleMessage,
)


def _domain_result() -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-1",
                facts={"title": "drink water"},
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="confirm_execution",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("not_created",),
            allow_rephrase=True,
        ),
    )


def test_agent_run_result_has_domain_and_capability_result_collections():
    result = AgentRunResult(
        visible_messages=[VisibleMessage(message_type="text", content="Done")],
        post_analyze_input=None,
        domain_results=[_domain_result()],
        capability_results=[
            CapabilityResult(name="timezone", ok=True, content={"summary": "UTC"})
        ],
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status="ok"),
    )

    assert result.domain_results[0].domain == "reminder"
    assert result.capability_results[0].name == "timezone"
    assert not hasattr(result, "tool_results")
