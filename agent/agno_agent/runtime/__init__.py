from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    DeferredActionPayload,
    ReminderFirePayload,
    UserTurnPayload,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)
from agent.agno_agent.runtime.selector import (
    RuntimeSelectionInput,
    RuntimeVersion,
    select_runtime,
)

__all__ = [
    "AgentInput",
    "AgentRunContext",
    "AgentRunResult",
    "CapabilityResult",
    "DeferredActionPayload",
    "OutputDisposition",
    "ReminderFirePayload",
    "RuntimeErrorDisposition",
    "RuntimeSelectionInput",
    "RuntimeVersion",
    "run_agent_runtime_event",
    "run_deferred_action_runtime_event",
    "select_runtime",
    "TrustedCharacterContext",
    "TrustedConversationContext",
    "TrustedRelationContext",
    "TrustedUserContext",
    "UserTurnPayload",
    "VisibleMessage",
]


def __getattr__(name: str):
    if name not in {
        "run_agent_runtime_event",
        "run_deferred_action_runtime_event",
    }:
        raise AttributeError(name)

    from agent.agno_agent.runtime.event_adapter import (
        run_agent_runtime_event,
        run_deferred_action_runtime_event,
    )

    return {
        "run_agent_runtime_event": run_agent_runtime_event,
        "run_deferred_action_runtime_event": run_deferred_action_runtime_event,
    }[name]
