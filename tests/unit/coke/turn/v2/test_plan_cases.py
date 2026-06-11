from __future__ import annotations

from typing import Any, Mapping

import pytest

from coke.turn.v2.plan import PlanRequest, SiliconFlowPlanner

PlanCase = tuple[str, str, tuple[Mapping[str, Any], ...], str]

CASES: tuple[PlanCase, ...] = (
    (
        "zh plain reminder list",
        "列一下我的提醒",
        ({"domain": "reminder", "operation": "list", "params": {}},),
        "reply_needed",
    ),
    (
        "en plain reminder list",
        "show my reminders",
        ({"domain": "reminder", "operation": "list", "params": {}},),
        "reply_needed",
    ),
    (
        "zh reminder count as list",
        "我现在有几个提醒",
        ({"domain": "reminder", "operation": "list", "params": {}},),
        "reply_needed",
    ),
    (
        "zh filtered reminder list",
        "看一下今天的提醒",
        ({"domain": "reminder", "operation": "list", "params": {"keyword": "今天"}},),
        "reply_needed",
    ),
    (
        "en filtered reminder list",
        "show my work reminders",
        ({"domain": "reminder", "operation": "list", "params": {"keyword": "work"}},),
        "reply_needed",
    ),
    (
        "zh create reminder",
        "提醒我明天九点跑步",
        (
            {
                "domain": "reminder",
                "operation": "create",
                "params": {"content": "跑步", "time_phrase": "明天九点"},
            },
        ),
        "reply_needed",
    ),
    (
        "en create reminder",
        "remind me tomorrow to call mom",
        (
            {
                "domain": "reminder",
                "operation": "create",
                "params": {"content": "call mom", "time_phrase": "tomorrow"},
            },
        ),
        "reply_needed",
    ),
    (
        "zh batch create reminders",
        "提醒我买牛奶，也提醒我给妈妈打电话",
        (
            {
                "domain": "reminder",
                "operation": "batch_create",
                "params": {
                    "items": [
                        {"content": "买牛奶"},
                        {"content": "给妈妈打电话"},
                    ]
                },
            },
        ),
        "reply_needed",
    ),
    (
        "en batch create reminders",
        "remind me to submit expenses and book tickets",
        (
            {
                "domain": "reminder",
                "operation": "batch_create",
                "params": {
                    "items": [
                        {"content": "submit expenses"},
                        {"content": "book tickets"},
                    ]
                },
            },
        ),
        "reply_needed",
    ),
    (
        "zh update reminder by keyword",
        "把健身提醒改成明天晚上",
        (
            {
                "domain": "reminder",
                "operation": "update",
                "params": {"match": "健身", "time_phrase": "明天晚上"},
            },
        ),
        "reply_needed",
    ),
    (
        "en update reminder by keyword",
        "move the gym reminder to tomorrow night",
        (
            {
                "domain": "reminder",
                "operation": "update",
                "params": {"match": "gym", "time_phrase": "tomorrow night"},
            },
        ),
        "reply_needed",
    ),
    (
        "zh delete reminder by keyword",
        "删掉健身提醒",
        ({"domain": "reminder", "operation": "delete", "params": {"match": "健身"}},),
        "reply_needed",
    ),
    (
        "en delete reminder by keyword",
        "delete my gym reminder",
        ({"domain": "reminder", "operation": "delete", "params": {"match": "gym"}},),
        "reply_needed",
    ),
    (
        "zh complete reminder by keyword",
        "健身提醒已经做完了",
        (
            {
                "domain": "reminder",
                "operation": "complete",
                "params": {"match": "健身"},
            },
        ),
        "reply_needed",
    ),
    (
        "en complete reminder by keyword",
        "mark the gym reminder done",
        ({"domain": "reminder", "operation": "complete", "params": {"match": "gym"}},),
        "reply_needed",
    ),
    (
        "zh shared reminder create",
        "明天提醒小王交报告",
        (
            {
                "domain": "social_scheduling",
                "operation": "create_shared_reminder",
                "params": {
                    "participant": "小王",
                    "content": "交报告",
                    "time_phrase": "明天",
                },
            },
        ),
        "reply_needed",
    ),
    (
        "en shared reminder create",
        "remind Amy tomorrow to send the deck",
        (
            {
                "domain": "social_scheduling",
                "operation": "create_shared_reminder",
                "params": {
                    "participant": "Amy",
                    "content": "send the deck",
                    "time_phrase": "tomorrow",
                },
            },
        ),
        "reply_needed",
    ),
    (
        "zh shared reminder cancel",
        "取消给小王的报告提醒",
        (
            {
                "domain": "social_scheduling",
                "operation": "cancel_shared_reminder",
                "params": {"participant": "小王", "match": "报告"},
            },
        ),
        "reply_needed",
    ),
    (
        "zh shared reminder time-only reschedule",
        "把我和 lizihao 的 openCoke 共享提醒改到明天下午4点",
        (
            {
                "domain": "social_scheduling",
                "operation": "update_shared_reminder",
                "params": {
                    "participant": "lizihao",
                    "match": "openCoke",
                    "time_phrase": "明天下午4点",
                },
            },
        ),
        "reply_needed",
    ),
    (
        "en list shared reminders",
        "show shared reminders with Amy",
        (
            {
                "domain": "social_scheduling",
                "operation": "list_shared",
                "params": {"participant": "Amy"},
            },
        ),
        "reply_needed",
    ),
    (
        "zh availability query",
        "小王明天下午有空吗",
        (
            {
                "domain": "social_scheduling",
                "operation": "availability_query",
                "params": {
                    "participant": "小王",
                    "local_start": "2026-06-11T13:00:00",
                    "local_end": "2026-06-11T18:00:00",
                },
            },
        ),
        "reply_needed",
    ),
    (
        "zh friend list",
        "我的好友有哪些",
        ({"domain": "friendship", "operation": "list_friends", "params": {}},),
        "reply_needed",
    ),
    (
        "en add friend by code",
        "add friend code ABC123",
        (
            {
                "domain": "friendship",
                "operation": "add_via_code",
                "params": {"code": "ABC123"},
            },
        ),
        "reply_needed",
    ),
    (
        "zh get friend link",
        "给我好友邀请链接",
        ({"domain": "friendship", "operation": "get_friend_link", "params": {}},),
        "reply_needed",
    ),
    (
        "en remove friend",
        "remove Amy from friends",
        (
            {
                "domain": "friendship",
                "operation": "remove_friend",
                "params": {"friend": "Amy"},
            },
        ),
        "reply_needed",
    ),
    (
        "zh set timezone",
        "把我的时区改成东京",
        (
            {
                "domain": "settings",
                "operation": "set_timezone",
                "params": {"timezone_text": "东京"},
            },
        ),
        "reply_needed",
    ),
    (
        "en toggle proactive",
        "turn proactive reminders off",
        (
            {
                "domain": "settings",
                "operation": "toggle_proactive",
                "params": {"enabled": False},
            },
        ),
        "reply_needed",
    ),
    (
        "zh toggle memory",
        "不要记住这些偏好",
        (
            {
                "domain": "settings",
                "operation": "toggle_memory",
                "params": {"enabled": False},
            },
        ),
        "reply_needed",
    ),
    (
        "en update settings",
        "use concise replies",
        (
            {
                "domain": "settings",
                "operation": "update_settings",
                "params": {"preference": "concise replies"},
            },
        ),
        "reply_needed",
    ),
    (
        "zh calendar import",
        "导入这个日历",
        (
            {
                "domain": "calendar_import",
                "operation": "import",
                "params": {"source": "current_attachment"},
            },
        ),
        "reply_needed",
    ),
    ("zh greeting", "你好", (), "reply_needed"),
    ("en greeting", "hi Coke", (), "reply_needed"),
    ("zh intentional no reply", "嗯", (), "intentional_no_reply"),
    ("en intentional no reply", "ok", (), "intentional_no_reply"),
)


@pytest.mark.parametrize(
    ("label", "message", "actions", "reply_necessity"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_planner_case_corpus_uses_expected_action_shape(
    label: str,
    message: str,
    actions: tuple[Mapping[str, Any], ...],
    reply_necessity: str,
) -> None:
    client = StubJSONClient(
        {
            "actions": list(actions),
            "reply_necessity": reply_necessity,
        }
    )

    plan = SiliconFlowPlanner(client).plan(_request(message))

    assert [(action.domain, action.operation) for action in plan.actions] == [
        (action["domain"], action["operation"]) for action in actions
    ], label
    assert [dict(action.params) for action in plan.actions] == [
        dict(action["params"]) for action in actions
    ], label
    assert plan.reply_necessity == reply_necessity


class StubJSONClient:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload

    def complete_json(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> Mapping[str, Any]:
        return self.payload


def _request(text: str) -> PlanRequest:
    return PlanRequest(
        account_id="acct-1",
        conversation_id="conv-1",
        payload={"text": text},
        trusted_facts={"timezone": "Asia/Tokyo"},
    )
