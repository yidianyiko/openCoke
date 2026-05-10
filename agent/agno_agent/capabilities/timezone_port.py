from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


class TimezonePort:
    def __init__(
        self,
        handler: (
            Callable[[str, AgentRunContext, dict[str, Any]], dict[str, Any]] | None
        ) = None,
    ) -> None:
        self.handler = handler

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        args = _normalize_timezone_args(args or {})
        if self.handler is None:
            from agent.agno_agent.tools.timezone_tools import (
                consume_timezone_confirmation,
                set_user_timezone,
                store_timezone_proposal,
            )

            def _default_handler(
                text: str,
                context: AgentRunContext,
                request_args: dict[str, Any],
            ) -> dict[str, Any]:
                session_state = {
                    "user": {
                        "id": context.user.id,
                        "timezone": context.user.timezone,
                    },
                    "conversation": {
                        "id": context.conversation.id,
                        "_id": context.conversation.id,
                    },
                }
                action = str(request_args.get("action") or "").strip()
                if action == "direct_set":
                    return set_user_timezone.entrypoint(
                        timezone=str(request_args.get("timezone") or ""),
                        session_state=session_state,
                    )
                if action == "proposal":
                    return store_timezone_proposal.entrypoint(
                        timezone=str(request_args.get("timezone") or ""),
                        session_state=session_state,
                    )
                if action == "confirm":
                    return consume_timezone_confirmation.entrypoint(
                        decision=str(request_args.get("decision") or ""),
                        session_state=session_state,
                    )
                return {
                    "ok": False,
                    "message": f"unsupported timezone action: {action}",
                }

            self.handler = _default_handler

        content = dict(self.handler(input_message, run_context, args))
        ok = bool(content.get("ok", True))
        message = content.get("message")
        if (
            ok
            and isinstance(message, str)
            and message.strip()
            and not content.get("summary")
        ):
            content["summary"] = message.strip()
        if (
            ok
            and isinstance(message, str)
            and message.strip()
            and not content.get("visible_summary")
        ):
            content["visible_summary"] = message.strip()
        return CapabilityResult(
            name="timezone",
            ok=ok,
            content=content,
            metadata={"durable_write": bool(content.get("state"))},
        )


def _normalize_timezone_args(args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    action = str(normalized.get("action") or "").strip().lower()
    action_aliases = {
        "set": "direct_set",
        "update": "direct_set",
        "change": "direct_set",
        "direct": "direct_set",
        "direct-set": "direct_set",
        "direct set": "direct_set",
        "propose": "proposal",
        "ask": "proposal",
        "confirm_yes": "confirm",
        "confirm_no": "confirm",
    }
    normalized["action"] = action_aliases.get(action, action)
    return normalized
