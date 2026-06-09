from __future__ import annotations

from coke.turn.reminder_list_render import render_reminder_list_reply


def test_render_reminder_list_reply_matches_current_chinese_template():
    facts = {
        "count": 2,
        "reminders": [
            {"content": "买牛奶", "display_time_label": "今天 18:00"},
            {"content": "给妈妈打电话"},
        ],
    }

    assert (
        render_reminder_list_reply(
            facts,
            user_text="列一下我的提醒",
            account_id="account_1",
        )
        == "你现在一共有 2 个提醒：\n"
        "1. 买牛奶（今天 18:00）\n"
        "2. 给妈妈打电话（未设定时间）"
    )


def test_render_reminder_list_reply_matches_current_english_template():
    facts = {
        "count": 2,
        "reminders": [
            {"content": "buy milk", "display_time_label": "Today 6:00 PM"},
            {"content": "call mom"},
        ],
    }

    assert (
        render_reminder_list_reply(
            facts,
            user_text="list my reminders",
            account_id="account_1",
        )
        == "You currently have 2 reminders:\n"
        "1. buy milk (Today 6:00 PM)\n"
        "2. call mom (unscheduled)"
    )
