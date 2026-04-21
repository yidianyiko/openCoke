def test_deferred_action_message_source_context_uses_reminder_template():
    from agent.prompt import chat_contextprompt

    context = {
        "user": {"nickname": "Alice"},
        "system_message_metadata": {"kind": "user_reminder"},
    }

    rendered = chat_contextprompt.get_message_source_context(
        "deferred_action",
        context,
    )

    assert "scheduled reminder" in rendered
    assert "not a message sent by Alice" in rendered


def test_deferred_action_message_source_context_uses_followup_template():
    from agent.prompt import chat_contextprompt

    context = {
        "user": {"nickname": "Alice"},
        "system_message_metadata": {"kind": "proactive_followup"},
    }

    rendered = chat_contextprompt.get_message_source_context(
        "deferred_action",
        context,
    )

    assert "initiating the conversation" in rendered
    assert "not a message sent by Alice" in rendered


def test_message_util_treats_deferred_actions_as_proactive_outputs(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["message_source"] = "deferred_action"
    sample_context["system_message_metadata"] = {"kind": "user_reminder"}
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["platform"] = "wechat_personal"
    sample_context["conversation"]["conversation_info"]["input_messages"] = []

    monkeypatch.setattr(
        message_util,
        "build_clawscale_push_metadata",
        lambda *args, **kwargs: {
            "business_conversation_key": "bc_1",
            "output_id": "out_1",
            "delivery_mode": "push",
        },
    )
    monkeypatch.setattr(
        message_util,
        "send_message",
        lambda platform, from_user, to_user, chatroom_name, message, **kwargs: {
            "platform": platform,
            "from_user": from_user,
            "to_user": to_user,
            "chatroom_name": chatroom_name,
            "metadata": kwargs["metadata"],
            "account_id": kwargs.get("account_id"),
            "message": message,
        },
    )

    output = message_util.send_message_via_context(sample_context, "提醒你喝水")

    assert output["platform"] is None
    assert output["from_user"] is None
    assert output["to_user"] is None
    assert output["chatroom_name"] is None
    assert output["account_id"] == sample_context["user"]["id"]
    assert output["metadata"]["delivery_mode"] == "push"
