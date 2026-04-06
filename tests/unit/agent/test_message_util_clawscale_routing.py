def test_message_util_appends_push_metadata_for_proactive_output(
    monkeypatch, sample_context
):
    from agent.util import message_util

    monkeypatch.setattr(
        message_util,
        "build_clawscale_push_metadata",
        lambda user_id, now_ts=None: {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
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
            "message": message,
            "metadata": kwargs["metadata"],
        },
    )

    sample_context["conversation"]["platform"] = "wechat"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["conversation_info"]["input_messages"] = []
    message = message_util.send_message_via_context(sample_context, "提醒你喝水")

    assert message["metadata"]["route_via"] == "clawscale"
    assert message["metadata"]["delivery_mode"] == "push"
