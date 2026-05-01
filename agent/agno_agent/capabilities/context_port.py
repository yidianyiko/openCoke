from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _plain_value(value[key])
            for key in sorted(value.keys(), key=lambda item: str(item))
        }
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return value


class ContextPort:
    def build_base_context(self, run_context: AgentRunContext) -> dict[str, Any]:
        base_context = {
            "user": {
                "id": run_context.user.id,
                "nickname": run_context.user.nickname,
                "timezone": run_context.user.timezone,
            },
            "character": {
                "id": run_context.character.id,
                "nickname": run_context.character.nickname,
            },
            "conversation": {
                "id": run_context.conversation.id,
                "platform": run_context.conversation.platform,
                "route_key": run_context.conversation.route_key,
            },
            "relation": {
                "uid": run_context.relation.uid,
                "cid": run_context.relation.cid,
            },
            "current_time": run_context.current_time.isoformat(),
            "recent_chat_history": run_context.recent_chat_history,
        }

        if run_context.runtime_metadata:
            base_context["runtime_metadata"] = _plain_value(
                run_context.runtime_metadata
            )

        return base_context
