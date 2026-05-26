from datetime import UTC, datetime
import sys
import types
from types import SimpleNamespace

sys.modules.setdefault("agent.agno_agent.agents", types.ModuleType("agents"))

from agent.agno_agent.runtime.context import AgentRunContext


def _run_context(user_id: str = "ck_a"):
    return AgentRunContext(
        user=SimpleNamespace(id=user_id, nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        relation=SimpleNamespace(uid=user_id, cid="char_1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
    )


def test_get_user_link_calls_gateway_tool_with_trusted_customer_identity():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    calls = []

    def handler(tool_name, payload):
        calls.append((tool_name, payload))
        return {"ok": True, "data": {"url": "https://kap.example/u/AbCdEfGhIjK_"}}

    port = SchedulingCapabilityPort(tool_name="get_user_link", handler=handler)
    result = port.run(
        "show my link",
        _run_context(),
        {"customer_id": "spoofed", "target_account_id": "ck_b"},
    )

    assert result.ok is True
    assert result.name == "get_user_link"
    assert result.content["url"] == "https://kap.example/u/AbCdEfGhIjK_"
    assert calls == [
        (
            "get_user_link",
            {
                "customer_id": "ck_a",
                "target_account_id": "ck_b",
                "conversation_id": "conv_1",
                "platform": "business",
                "input_message": "show my link",
            },
        )
    ]


def test_get_user_link_provides_visible_summary_for_empty_chat_text():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": {
                "url": "https://kap.example/u/AbCdEfGhIjK_",
                "code": "AbCdEfGhIjK_",
            },
        }

    port = SchedulingCapabilityPort(tool_name="get_user_link", handler=handler)
    result = port.run("把我自己的好友邀请链接给我", _run_context(), {})

    assert result.ok is True
    assert result.content["visible_summary"] == (
        "这是你的好友邀请链接：https://kap.example/u/AbCdEfGhIjK_"
    )
    assert result.visible_summary == (
        "这是你的好友邀请链接：https://kap.example/u/AbCdEfGhIjK_"
    )


def test_list_pending_shared_reminders_provides_visible_summary():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": [
                {
                    "id": "sr_1",
                    "requesterAccountId": "ck_alice",
                    "requester": {"displayName": "Alice Smoke"},
                    "title": "跑步",
                    "fireAt": "2026-05-29T10:30:00.000Z",
                    "status": "pending_invitee_confirmation",
                }
            ],
        }

    port = SchedulingCapabilityPort(
        tool_name="list_pending_shared_reminders",
        handler=handler,
    )
    result = port.run("我现在有没有待处理的共享提醒？", _run_context(), {})

    assert result.ok is True
    assert result.content["visible_summary"] == (
        "你有 1 个待处理的共享提醒：Alice Smoke 发来的“跑步”。"
    )
    assert result.visible_summary == "你有 1 个待处理的共享提醒：Alice Smoke 发来的“跑步”。"


def test_list_pending_shared_reminders_empty_summary():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {"ok": True, "data": []}

    port = SchedulingCapabilityPort(
        tool_name="list_pending_shared_reminders",
        handler=handler,
    )
    result = port.run("我现在有没有待处理的共享提醒？", _run_context(), {})

    assert result.ok is True
    assert result.content["visible_summary"] == "目前没有待处理的共享提醒。"


def test_list_shared_reminders_provides_visible_summary():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": {
                "friend_name": "Bob",
                "shared_reminders": [
                    {
                        "id": "srr_1",
                        "title": "打羽毛球",
                        "status": "accepted",
                        "fireAt": "2026-05-25T08:00:00.000Z",
                        "timezone": "Asia/Tokyo",
                        "requester": {"displayName": "Alice Badminton"},
                        "invitee": {"displayName": "Bob Badminton"},
                    }
                ],
            },
        }

    port = SchedulingCapabilityPort(
        tool_name="list_shared_reminders",
        handler=handler,
    )
    result = port.run(
        "我和 Bob 的共享提醒现在是什么状态？",
        _run_context(),
        {"friend_name": "Bob", "status": "accepted"},
    )

    assert result.ok is True
    assert result.content["visible_summary"] == (
        "你有 1 个共享提醒：Bob 的“打羽毛球”，2026-05-25 17:00，状态 accepted。"
    )
    assert result.visible_summary == (
        "你有 1 个共享提醒：Bob 的“打羽毛球”，2026-05-25 17:00，状态 accepted。"
    )


def test_list_shared_reminders_summary_prefers_viewer_display_fields():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": {
                "friend_name": "Mei",
                "shared_reminders": [
                    {
                        "id": "srr_1",
                        "title": "喝咖啡",
                        "status": "pending_invitee_confirmation",
                        "fireAt": "2026-05-27T01:00:00.000Z",
                        "timezone": "UTC",
                        "viewer_timezone": "Asia/Tokyo",
                        "viewer_local_date": "2026-05-27",
                        "viewer_local_time": "10:00",
                    }
                ],
            },
        }

    port = SchedulingCapabilityPort(
        tool_name="list_shared_reminders",
        handler=handler,
    )
    result = port.run("我有哪些共享提醒？", _run_context(), {})

    assert result.ok is True
    assert "2026-05-27 10:00" in result.visible_summary
    assert "01:00" not in result.visible_summary


def test_list_shared_reminders_payload_includes_account_timezone_for_viewer_display():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {"ok": True, "data": {"shared_reminders": []}}

    port = SchedulingCapabilityPort(
        tool_name="list_shared_reminders",
        handler=handler,
    )
    result = port.run("我有哪些共享提醒？", _run_context(), {})

    assert result.ok is True
    assert captured["payload"]["timezone"] == "Asia/Shanghai"


def test_list_friend_requests_empty_summary():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {"ok": True, "data": []}

    port = SchedulingCapabilityPort(
        tool_name="list_friend_requests",
        handler=handler,
    )
    result = port.run("我现在有没有未处理的好友请求或系统通知？", _run_context(), {})

    assert result.ok is True
    assert result.content["visible_summary"] == "目前没有待处理的好友请求。"


def test_list_friend_requests_summary_includes_names_and_direction():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": [
                {
                    "id": "fr_in",
                    "requesterAccountId": "ck_bob",
                    "targetAccountId": "ck_a",
                    "status": "pending",
                    "requester": {"displayName": "Bob Smoke"},
                    "target": {"displayName": "Alice Smoke"},
                },
                {
                    "id": "fr_out",
                    "requesterAccountId": "ck_a",
                    "targetAccountId": "ck_carol",
                    "status": "pending",
                    "requester": {"displayName": "Alice Smoke"},
                    "target": {"displayName": "Carol Smoke"},
                },
                {
                    "id": "fr_old",
                    "requesterAccountId": "ck_dan",
                    "targetAccountId": "ck_a",
                    "status": "rejected",
                    "requester": {"displayName": "Dan Smoke"},
                    "target": {"displayName": "Alice Smoke"},
                },
            ],
        }

    port = SchedulingCapabilityPort(
        tool_name="list_friend_requests",
        handler=handler,
    )
    result = port.run("我的好友申请", _run_context(), {})

    assert result.ok is True
    assert result.content["visible_summary"] == (
        "你有 3 个好友请求：收到 Bob Smoke 的申请；已向 Carol Smoke 发出申请。"
    )


def test_list_friend_requests_terminal_only_summary_marks_history():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": [
                {
                    "id": "fr_1",
                    "status": "rejected",
                    "requesterAccountId": "ck_b",
                    "targetAccountId": "ck_a",
                    "requester": {"displayName": "Bob Smoke"},
                    "target": {"displayName": "Alice Smoke"},
                }
            ],
        }

    port = SchedulingCapabilityPort(
        tool_name="list_friend_requests",
        handler=handler,
    )
    result = port.run("我的好友申请", _run_context(user_id="ck_a"), {})

    assert result.ok is True
    assert result.content["visible_summary"] == (
        "你有 1 个好友请求：历史：Bob Smoke，收到方向，状态 rejected。"
    )


def test_list_friends_empty_summary():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {"ok": True, "data": []}

    port = SchedulingCapabilityPort(
        tool_name="list_friends",
        handler=handler,
    )
    result = port.run("看看我现在的好友列表。", _run_context(), {})

    assert result.ok is True
    assert result.content["visible_summary"] == "你现在还没有好友。"


def test_list_friends_summary_includes_counterpart_names():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": [
                {
                    "id": "fs_1",
                    "status": "active",
                    "accountAId": "ck_a",
                    "accountBId": "ck_b",
                    "accountA": {"displayName": "Alice Smoke"},
                    "accountB": {"displayName": "Bob Smoke"},
                },
                {
                    "id": "fs_2",
                    "status": "active",
                    "accountAId": "ck_c",
                    "accountBId": "ck_a",
                    "accountA": {"displayName": "Carol Smoke"},
                    "accountB": {"displayName": "Alice Smoke"},
                },
            ],
        }

    port = SchedulingCapabilityPort(
        tool_name="list_friends",
        handler=handler,
    )
    result = port.run("我有哪些好友？", _run_context(user_id="ck_a"), {})

    assert result.ok is True
    assert result.content["visible_summary"] == (
        "你现在有 2 个好友：Bob Smoke；Carol Smoke。"
    )


def test_friend_name_ambiguous_failure_has_safe_visible_summary():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {"ok": False, "error": "friend_name_ambiguous", "data": {}}

    port = SchedulingCapabilityPort(
        tool_name="list_friend_calendar_facts",
        handler=handler,
    )
    result = port.run("看看 Bob 这周哪些时间空？", _run_context(), {})

    assert result.ok is False
    assert result.content["visible_summary"] == "有多个同名好友，请提供完整好友名称。"


def test_create_shared_reminder_forwards_required_args():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {
            "ok": True,
            "data": {"id": "srr_1", "status": "pending_invitee_confirmation"},
        }

    port = SchedulingCapabilityPort(tool_name="create_shared_reminder", handler=handler)
    result = port.run(
        "Help me and A remember the meeting",
        _run_context(user_id="acct_b"),
        {
            "invitee_account_id": "acct_a",
            "title": "meeting",
            "fire_at": "2026-05-22T07:00:00.000Z",
            "timezone": "Asia/Shanghai",
            "idempotency_key": "shared-1",
        },
    )

    assert result.ok is True
    assert captured["tool_name"] == "create_shared_reminder"
    assert captured["payload"]["customer_id"] == "acct_b"
    assert captured["payload"]["invitee_account_id"] == "acct_a"
    assert result.durable_write is True


def test_create_shared_reminder_injects_account_timezone_when_model_omits_it():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {
            "ok": True,
            "data": {"id": "srr_1", "status": "pending_invitee_confirmation"},
        }

    port = SchedulingCapabilityPort(tool_name="create_shared_reminder", handler=handler)
    result = port.run(
        "约 Nora 明天 10 点喝咖啡",
        _run_context(user_id="acct_b"),
        {
            "invitee_name": "Nora",
            "title": "喝咖啡",
            "fire_at": "2026-05-27T01:00:00.000Z",
            "idempotency_key": "shared-1",
        },
    )

    assert result.ok is True
    assert captured["payload"]["timezone"] == "Asia/Shanghai"


def test_create_shared_reminder_preserves_explicit_timezone():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {
            "ok": True,
            "data": {"id": "srr_1", "status": "pending_invitee_confirmation"},
        }

    port = SchedulingCapabilityPort(tool_name="create_shared_reminder", handler=handler)
    result = port.run(
        "Schedule with Nora",
        _run_context(user_id="acct_b"),
        {
            "invitee_name": "Nora",
            "title": "meeting",
            "fire_at": "2026-05-27T17:00:00.000Z",
            "timezone": "America/Los_Angeles",
            "idempotency_key": "shared-1",
        },
    )

    assert result.ok is True
    assert captured["payload"]["timezone"] == "America/Los_Angeles"


def test_send_friend_request_does_not_treat_note_message_as_visible_summary():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": {
                "id": "fr_1",
                "status": "pending",
                "message": "跑步搭子",
            },
        }

    port = SchedulingCapabilityPort(
        tool_name="send_friend_request_by_user_link_code",
        handler=handler,
    )

    result = port.run(
        "我要加好友，链接码 AbCdEfGhIjK_，备注：跑步搭子。",
        _run_context(),
        {"user_link_code": "AbCdEfGhIjK_", "message": "跑步搭子"},
    )

    assert result.ok is True
    assert result.content["message"] == "跑步搭子"
    assert result.content["visible_summary"] == "已发送好友请求。"
    assert result.visible_summary == "已发送好友请求。"


def test_write_tools_generate_idempotency_key_when_model_omits_it():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {"ok": True, "data": {"id": "srr_1"}}

    port = SchedulingCapabilityPort(tool_name="create_shared_reminder", handler=handler)
    result = port.run(
        "Help me and Nora remember the meeting",
        _run_context(user_id="acct_b"),
        {
            "invitee_name": "Nora",
            "title": "meeting",
            "fire_at": "2026-05-22T07:00:00.000Z",
            "timezone": "Asia/Shanghai",
        },
    )

    assert result.ok is True
    assert captured["payload"]["idempotency_key"].startswith("create_shared_reminder:")


def test_list_friend_calendar_facts_is_read_only_and_forwards_range_args():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {
            "ok": True,
            "data": {
                "target_account_id": "acct_a",
                "range": {
                    "from": "2026-05-25",
                    "to": "2026-05-31",
                    "timezone": "Asia/Tokyo",
                },
                "busy_intervals": [],
                "privacy": {"event_details_included": False},
            },
        }

    port = SchedulingCapabilityPort(
        tool_name="list_friend_calendar_facts", handler=handler
    )
    result = port.run(
        "What free time does Coach A have this week?",
        _run_context(user_id="acct_b"),
        {
            "target_account_id": "acct_a",
            "from_date": "2026-05-25",
            "to_date": "2026-05-31",
            "timezone": "Asia/Tokyo",
        },
    )

    assert result.ok is True
    assert result.durable_write is False
    assert captured["tool_name"] == "list_friend_calendar_facts"
    assert captured["payload"]["customer_id"] == "acct_b"
    assert captured["payload"]["target_account_id"] == "acct_a"
    assert captured["payload"]["from_date"] == "2026-05-25"
    assert captured["payload"]["to_date"] == "2026-05-31"


def test_list_friend_calendar_facts_sanitizes_private_event_fields():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        del tool_name, payload
        return {
            "ok": True,
            "data": {
                "target_account_id": "acct_friend",
                "range": {
                    "from": "2026-05-25",
                    "to": "2026-05-31",
                    "timezone": "Asia/Tokyo",
                },
                "busy_intervals": [
                    {
                        "id": "rem_1",
                        "reminder_id": "rem_1",
                        "title": "康复课私密标题",
                        "prompt": "提醒具体内容",
                        "metadata": {"private": True},
                        "agent_output_target": {"conversation_id": "conv_private"},
                        "start": "2026-05-25T09:00:00+09:00",
                        "end": "2026-05-25T10:00:00+09:00",
                        "timezone": "Asia/Tokyo",
                    }
                ],
                "privacy": {"event_details_included": True},
            },
        }

    port = SchedulingCapabilityPort(
        tool_name="list_friend_calendar_facts",
        handler=handler,
    )

    result = port.run(
        "看看 Bob 这周哪些时间空？",
        _run_context(user_id="acct_me"),
        {
            "friend_name": "Bob",
            "from_date": "2026-05-25",
            "to_date": "2026-05-31",
            "timezone": "Asia/Tokyo",
        },
    )

    assert result.ok is True
    assert "target_account_id" not in result.content
    assert result.content["privacy"]["event_details_included"] is False
    assert result.content["range"]["timezone"] == "Asia/Tokyo"
    busy_interval = result.content["busy_intervals"][0]
    assert busy_interval == {
        "start": "2026-05-25T09:00:00+09:00",
        "end": "2026-05-25T10:00:00+09:00",
        "timezone": "Asia/Tokyo",
    }


def test_list_friend_calendar_facts_forwards_friend_name_when_target_account_id_is_missing():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {
            "ok": True,
            "data": {
                "target_account_id": "acct_a",
                "range": {
                    "from": "2026-05-25",
                    "to": "2026-05-31",
                    "timezone": "Asia/Tokyo",
                },
                "busy_intervals": [],
                "privacy": {"event_details_included": False},
            },
        }

    port = SchedulingCapabilityPort(tool_name="list_friend_calendar_facts", handler=handler)
    result = port.run(
        "What free time does Coach A have this week?",
        _run_context(user_id="acct_b"),
        {
            "friend_name": "Coach A",
            "from_date": "2026-05-25",
            "to_date": "2026-05-31",
            "timezone": "Asia/Tokyo",
        },
    )

    assert result.ok is True
    assert result.durable_write is False
    assert captured["tool_name"] == "list_friend_calendar_facts"
    assert captured["payload"]["customer_id"] == "acct_b"
    assert captured["payload"]["friend_name"] == "Coach A"
    assert "target_account_id" not in captured["payload"]


def test_scheduling_gateway_client_uses_internal_auth():
    from agent.agno_agent.capabilities.scheduling import SchedulingGatewayClient

    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "data": {"pending": []}}

    class Session:
        def post(self, url, json, headers, timeout):
            captured.update(
                {"url": url, "json": json, "headers": headers, "timeout": timeout}
            )
            return Response()

    client = SchedulingGatewayClient(
        api_url="https://api.example",
        api_key="internal-key",
        session=Session(),
    )

    assert client.call_tool(
        "list_pending_shared_reminders", {"customer_id": "ck_a"}
    ) == {
        "ok": True,
        "data": {"pending": []},
    }
    assert (
        captured["url"]
        == "https://api.example/api/internal/scheduling/tools/list_pending_shared_reminders"
    )
    assert captured["headers"]["Authorization"] == "Bearer internal-key"


def test_scheduling_gateway_client_returns_error_envelope():
    from agent.agno_agent.capabilities.scheduling import (
        SchedulingGatewayClient,
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": False, "error": "friendship_not_found"}

    class Session:
        def post(self, url, json, headers, timeout):
            return Response()

    client = SchedulingGatewayClient(
        api_url="https://api.example",
        api_key="internal-key",
        session=Session(),
    )

    assert client.call_tool("remove_friendship", {"customer_id": "ck_a"}) == {
        "ok": False,
        "error": "friendship_not_found",
    }


def test_port_turns_gateway_domain_error_into_model_visible_failure():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        return {"ok": False, "error": "friendship_not_found"}

    port = SchedulingCapabilityPort(tool_name="remove_friendship", handler=handler)

    result = port.run("remove old friend", _run_context(), {"friendship_id": "fs_1"})

    assert result.ok is False
    assert result.error == "friendship_not_found"
    assert result.visible_summary == "日程操作暂时无法完成。"
    assert result.durable_write is False


def test_port_turns_gateway_exception_into_model_visible_failure():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        raise RuntimeError("gateway unavailable")

    port = SchedulingCapabilityPort(tool_name="create_shared_reminder", handler=handler)

    result = port.run("create shared reminder", _run_context(), {})

    assert result.ok is False
    assert result.error == "gateway unavailable"
    assert result.visible_summary == "日程操作暂时无法完成。"
    assert result.durable_write is False
