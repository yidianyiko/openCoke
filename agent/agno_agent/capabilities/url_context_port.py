from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


class UrlContextPort:
    def __init__(
        self, url_reader: Callable[[str], dict[str, Any]] | None = None
    ) -> None:
        self.url_reader = url_reader

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        if self.url_reader is None:
            from agent.agno_agent.tools.url_reader import (
                extract_urls_content,
                format_url_context,
            )

            def _default_reader(text: str) -> dict[str, Any]:
                url_contents = extract_urls_content(text)
                return {
                    "items": [item.to_dict() for item in url_contents],
                    "context": format_url_context(url_contents),
                }

            self.url_reader = _default_reader

        content = self.url_reader(input_message)
        return CapabilityResult(
            name="url_context",
            ok=True,
            content=content,
            metadata={
                "durable_write": False,
                "conversation_id": run_context.conversation.id,
                "requires_response_synthesis": True,
            },
        )
