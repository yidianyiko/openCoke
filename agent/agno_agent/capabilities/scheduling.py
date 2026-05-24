from __future__ import annotations

import os
from hashlib import sha256
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult

SCHEDULING_TOOL_NAMES = (
    "get_user_link",
    "reset_user_link",
    "disable_user_link",
    "send_friend_request_by_user_link_code",
    "list_friend_requests",
    "accept_friend_request",
    "reject_friend_request",
    "cancel_friend_request",
    "list_friends",
    "list_friend_calendar_facts",
    "remove_friendship",
    "block_account",
    "unblock_account",
    "create_shared_reminder",
    "list_pending_shared_reminders",
    "accept_shared_reminder",
    "reject_shared_reminder",
    "cancel_shared_reminder",
)

_READ_ONLY_TOOL_NAMES = {
    "get_user_link",
    "list_friend_requests",
    "list_friends",
    "list_friend_calendar_facts",
    "list_pending_shared_reminders",
}

_DURABLE_WRITE_VISIBLE_SUMMARIES = {
    "reset_user_link": "已重置用户链接。",
    "disable_user_link": "已停用用户链接。",
    "send_friend_request_by_user_link_code": "已发送好友请求。",
    "accept_friend_request": "已通过好友请求。",
    "reject_friend_request": "已拒绝好友请求。",
    "cancel_friend_request": "已取消好友请求。",
    "remove_friendship": "已移除好友关系。",
    "block_account": "已屏蔽该用户。",
    "unblock_account": "已解除屏蔽。",
    "create_shared_reminder": "已提交共享提醒请求。",
    "accept_shared_reminder": "已接受共享提醒。",
    "reject_shared_reminder": "已拒绝共享提醒并取消你的提醒。",
    "cancel_shared_reminder": "已取消共享提醒请求。",
}


class SchedulingGatewayClientError(RuntimeError):
    pass


class SchedulingGatewayClient:
    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_url = (api_url or _read_gateway_api_base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else _read_gateway_api_key()
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_url}/api/internal/scheduling/tools/{tool_name}",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        try:
            body = response.json()
        except ValueError as error:
            response.raise_for_status()
            raise SchedulingGatewayClientError(
                "invalid_scheduling_gateway_response"
            ) from error
        if not isinstance(body, dict):
            response.raise_for_status()
            raise SchedulingGatewayClientError("invalid_scheduling_gateway_response")
        if body.get("ok") is not True and getattr(response, "status_code", 200) >= 500:
            response.raise_for_status()
        return body


class SchedulingCapabilityPort:
    def __init__(
        self,
        *,
        tool_name: str,
        handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        client: SchedulingGatewayClient | None = None,
    ) -> None:
        if tool_name not in SCHEDULING_TOOL_NAMES:
            raise ValueError(f"unsupported scheduling tool: {tool_name}")
        self.tool_name = tool_name
        self.handler = handler
        self.client = client or SchedulingGatewayClient()

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        payload = _trusted_tool_payload(
            args or {},
            input_message=input_message,
            run_context=run_context,
            tool_name=self.tool_name,
        )
        try:
            raw = (
                self.handler(self.tool_name, payload)
                if self.handler
                else self.client.call_tool(self.tool_name, payload)
            )
        except Exception as error:
            return CapabilityResult(
                name=self.tool_name,
                ok=False,
                content={"summary": "日程操作暂时无法完成。"},
                error=str(error) or "scheduling_failed",
                metadata={
                    "durable_write": False,
                    "requires_response_synthesis": True,
                },
            )
        ok = raw.get("ok", True)
        data = raw.get("data", raw)
        if not isinstance(data, Mapping):
            data = {"value": data}
        content = dict(data)
        durable_write = self.tool_name not in _READ_ONLY_TOOL_NAMES
        if ok and durable_write and not _has_visible_summary(content):
            content["visible_summary"] = _DURABLE_WRITE_VISIBLE_SUMMARIES[
                self.tool_name
            ]
        if not ok and not _has_visible_summary(content):
            content["summary"] = "日程操作暂时无法完成。"
        return CapabilityResult(
            name=self.tool_name,
            ok=bool(ok),
            content=content,
            error=None if ok else str(raw.get("error") or "scheduling_failed"),
            metadata={
                "durable_write": bool(ok) and durable_write,
                "requires_response_synthesis": True,
            },
        )


def _trusted_tool_payload(
    args: dict[str, Any],
    *,
    input_message: str,
    run_context: AgentRunContext,
    tool_name: str,
) -> dict[str, Any]:
    payload = dict(args)
    if tool_name not in _READ_ONLY_TOOL_NAMES and not str(payload.get("idempotency_key") or "").strip():
        seed = f"{run_context.user.id}:{run_context.conversation.id}:{tool_name}:{input_message}"
        payload["idempotency_key"] = f"{tool_name}:{sha256(seed.encode()).hexdigest()[:32]}"
    payload.update(
        {
            "customer_id": run_context.user.id,
            "conversation_id": run_context.conversation.id,
            "platform": run_context.platform,
            "input_message": input_message,
        }
    )
    return payload


def _has_visible_summary(content: Mapping[str, Any]) -> bool:
    for key in ("visible_summary", "summary", "message"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _read_gateway_api_base_url() -> str:
    base = (
        os.environ.get("COKE_GATEWAY_API_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_COKE_API_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_API_URL", "").strip()
    )
    if base:
        return base

    try:
        from conf.config import CONF

        identity_api_url = str(
            CONF.get("clawscale_bridge", {}).get("identity_api_url") or ""
        ).strip()
        if identity_api_url:
            parsed = urlsplit(identity_api_url)
            return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    except Exception:
        pass
    return "http://127.0.0.1:4041"


def _read_gateway_api_key() -> str:
    api_key = os.environ.get("CLAWSCALE_IDENTITY_API_KEY", "").strip()
    if api_key:
        return api_key

    try:
        from conf.config import CONF

        return str(
            CONF.get("clawscale_bridge", {}).get("identity_api_key") or ""
        ).strip()
    except Exception:
        return ""
