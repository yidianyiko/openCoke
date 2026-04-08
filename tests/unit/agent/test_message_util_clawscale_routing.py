def test_message_util_uses_clawscale_route_metadata_for_proactive_output_without_inbound_input_metadata(
    monkeypatch, sample_context
):
    from agent.util import message_util

    sample_context["message_source"] = "future"
    sample_context["conversation_id"] = "conv_1"
    sample_context["conversation"]["platform"] = "wechat_personal"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"metadata": {"legacy_inbound": "should_not_copy"}}
    ]

    monkeypatch.setattr(
        message_util,
        "build_clawscale_push_metadata",
        lambda user_id, now_ts=None, context=None: {
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

    message = message_util.send_message_via_context(sample_context, "提醒你喝水")

    assert message["metadata"]["route_via"] == "clawscale"
    assert message["metadata"]["delivery_mode"] == "push"
    assert "legacy_inbound" not in message["metadata"]


def test_message_util_does_not_auto_inject_route_metadata_for_non_proactive_empty_input_messages(
    monkeypatch, sample_context
):
    from agent.util import message_util

    sample_context["message_source"] = "user"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["platform"] = "wechat_personal"
    sample_context["conversation"]["conversation_info"]["input_messages"] = []

    def fail_if_called(*args, **kwargs):
        raise AssertionError("build_clawscale_push_metadata should not be called")

    monkeypatch.setattr(message_util, "build_clawscale_push_metadata", fail_if_called)
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

    message = message_util.send_message_via_context(sample_context, "普通回复")

    assert message["metadata"] == {}


def test_build_clawscale_push_metadata_normalizes_wechat_platform(
    monkeypatch, sample_context
):
    from agent.util import message_util

    captured = {}

    class FakeResolver:
        def __init__(self, external_identity_dao, clawscale_push_route_dao=None):
            captured["external_identity_dao"] = external_identity_dao
            captured["clawscale_push_route_dao"] = clawscale_push_route_dao

        def build_push_metadata(
            self,
            account_id,
            now_ts,
            conversation_id=None,
            platform=None,
        ):
            captured["account_id"] = account_id
            captured["now_ts"] = now_ts
            captured["conversation_id"] = conversation_id
            captured["platform"] = platform
            return {"route_via": "clawscale", "platform": platform}

    class FakeExternalIdentityDAO:
        def __init__(self, *args, **kwargs):
            pass

    class FakeClawscalePushRouteDAO:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(
        "connector.clawscale_bridge.output_route_resolver.OutputRouteResolver",
        FakeResolver,
    )
    monkeypatch.setattr(
        "dao.external_identity_dao.ExternalIdentityDAO", FakeExternalIdentityDAO
    )
    monkeypatch.setattr(
        "dao.clawscale_push_route_dao.ClawscalePushRouteDAO",
        FakeClawscalePushRouteDAO,
    )
    sample_context["conversation"]["platform"] = "wechat"
    sample_context["conversation"]["chatroom_name"] = None

    metadata = message_util.build_clawscale_push_metadata(
        str(sample_context["user"]["_id"]),
        now_ts=1710000000,
        context=sample_context,
    )

    assert metadata["platform"] == "wechat_personal"
    assert captured["platform"] == "wechat_personal"
