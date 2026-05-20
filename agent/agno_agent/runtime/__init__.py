from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    ReminderFirePayload,
    UserTurnPayload,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
    with_output_references,
)

__all__ = [
    "AgentInput",
    "AgentRunContext",
    "AgentRunResult",
    "CapabilityResult",
    "OutputDisposition",
    "ReminderFirePayload",
    "RuntimeErrorDisposition",
    "TrustedCharacterContext",
    "TrustedConversationContext",
    "TrustedRelationContext",
    "TrustedUserContext",
    "UserTurnPayload",
    "VisibleMessage",
    "run_agent_runtime_event",
    "with_output_references",
]


def __getattr__(name: str):
    if name != "run_agent_runtime_event":
        raise AttributeError(name)
    from agent.agno_agent.runtime.event_adapter import run_agent_runtime_event

    return run_agent_runtime_event
