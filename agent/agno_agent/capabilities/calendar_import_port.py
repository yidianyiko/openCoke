from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


class CalendarImportPort:
    def __init__(
        self,
        handler: Callable[[str, AgentRunContext, dict[str, Any]], dict[str, Any]]
        | None = None,
    ) -> None:
        self.handler = handler

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        args = args or {}
        if self.handler is None:
            import os

            from agent.agno_agent.tools.calendar_import_handoff import (
                create_calendar_import_handoff_link,
            )

            def _fallback_web_url(path: str) -> str:
                for key in (
                    "DOMAIN_CLIENT",
                    "NEXT_PUBLIC_COKE_API_URL",
                    "NEXT_PUBLIC_API_URL",
                    "COKE_WEB_ALLOWED_ORIGIN",
                ):
                    base_url = os.environ.get(key, "").strip().rstrip("/")
                    if base_url:
                        return f"{base_url}{path}"
                return path

            def _default_handler(
                text: str,
                context: AgentRunContext,
                request_args: dict[str, Any],
            ) -> dict[str, Any]:
                payload = request_args.get("handoff_payload")
                if isinstance(payload, dict) and payload:
                    try:
                        link = create_calendar_import_handoff_link(payload)
                    except Exception as exc:
                        return {
                            "ok": False,
                            "message": str(exc) or exc.__class__.__name__,
                        }
                else:
                    link = _fallback_web_url("/account/calendar-import")
                return {
                    "ok": True,
                    "link": link,
                    "message": (
                        "用户想导入 Google Calendar。请把这个入口链接发给用户："
                        f"{link}。说明打开后登录或验证邮箱，然后点击 Start Google "
                        "Calendar import 授权 Google。不要说导入已经完成。"
                    ),
                }

            self.handler = _default_handler

        content = self.handler(input_message, run_context, args)
        return CapabilityResult(
            name="calendar_import",
            ok=bool(content.get("ok", True)),
            content=content,
            metadata={"durable_write": False},
        )
