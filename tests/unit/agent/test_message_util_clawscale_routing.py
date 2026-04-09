from types import SimpleNamespace


def test_message_util_emits_business_only_output_doc_for_clawscale_proactive_message(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["message_source"] = "future"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["platform"] = "wechat_personal"
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"metadata": {"legacy_inbound": "should_not_copy"}}
    ]

    monkeypatch.setattr(
        message_util,
        "build_clawscale_push_metadata",
        lambda *args, **kwargs: {
            "business_conversation_key": "bc_1",
            "output_id": "out_1",
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "causal_inbound_event_id": "in_1",
        },
    )

    def fake_send_message(platform, from_user, to_user, chatroom_name, message, **kwargs):
        output = {
            "message": message,
            "message_type": kwargs["message_type"],
            "status": kwargs["status"],
            "handled_timestamp": kwargs["handled_timestamp"],
            "metadata": kwargs["metadata"],
        }
        if kwargs.get("account_id") is not None:
            output["account_id"] = kwargs["account_id"]
        if platform is not None:
            output["platform"] = platform
        if from_user is not None:
            output["from_user"] = from_user
        if to_user is not None:
            output["to_user"] = to_user
        if chatroom_name is not None:
            output["chatroom_name"] = chatroom_name
        return output

    monkeypatch.setattr(message_util, "send_message", fake_send_message)

    message = message_util.send_message_via_context(sample_context, "提醒你喝水")

    assert message["account_id"] == str(sample_context["user"]["_id"])
    assert "platform" not in message
    assert message["metadata"] == {
        "business_conversation_key": "bc_1",
        "output_id": "out_1",
        "delivery_mode": "push",
        "idempotency_key": "idem_1",
        "trace_id": "trace_1",
        "causal_inbound_event_id": "in_1",
    }
    assert "legacy_inbound" not in message["metadata"]


def test_message_util_marks_proactive_output_failed_when_business_key_missing(
    sample_context, monkeypatch
):
    from agent.util import message_util

    now_ts = 1710000000
    sample_context["message_source"] = "future"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["platform"] = "wechat"
    sample_context["conversation"]["conversation_info"]["input_messages"] = []

    logged_messages = []

    def fake_warning(msg, *args, **kwargs):
        logged_messages.append(msg % args if args else msg)

    monkeypatch.setattr(message_util, "build_clawscale_push_metadata", lambda *args, **kwargs: {})
    monkeypatch.setattr(message_util.time, "time", lambda: now_ts)
    monkeypatch.setattr(message_util.logger, "warning", fake_warning)

    def fake_send_message(platform, from_user, to_user, chatroom_name, message, **kwargs):
        output = {
            "message": message,
            "status": kwargs["status"],
            "handled_timestamp": kwargs["handled_timestamp"],
            "metadata": kwargs["metadata"],
        }
        if kwargs.get("account_id") is not None:
            output["account_id"] = kwargs["account_id"]
        if platform is not None:
            output["platform"] = platform
        return output

    monkeypatch.setattr(message_util, "send_message", fake_send_message)

    message = message_util.send_message_via_context(
        sample_context,
        "提醒你喝水",
        expect_output_timestamp=now_ts + 3600,
    )

    assert message["status"] == "failed"
    assert message["handled_timestamp"] == now_ts
    assert message["metadata"]["failure_reason"] == "missing_clawscale_business_conversation_key"
    assert message["metadata"]["delivery_mode"] == "push"
    assert "platform" not in message
    assert any(
        "missing_clawscale_business_conversation_key" in log_message
        for log_message in logged_messages
    )


def test_message_util_does_not_auto_inject_clawscale_metadata_for_non_proactive_messages(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["message_source"] = "user"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["platform"] = "wechat_personal"
    sample_context["conversation"]["conversation_info"]["input_messages"] = []

    def fail_if_called(*args, **kwargs):
        raise AssertionError("build_clawscale_push_metadata should not be called")

    monkeypatch.setattr(message_util, "build_clawscale_push_metadata", fail_if_called)

    def fake_send_message(platform, from_user, to_user, chatroom_name, message, **kwargs):
        output = {
            "message": message,
            "metadata": kwargs["metadata"],
        }
        if kwargs.get("account_id") is not None:
            output["account_id"] = kwargs["account_id"]
        if platform is not None:
            output["platform"] = platform
        return output

    monkeypatch.setattr(message_util, "send_message", fake_send_message)

    message = message_util.send_message_via_context(sample_context, "普通回复")

    assert message["metadata"] == {}
    assert "account_id" not in message


def test_build_clawscale_push_metadata_returns_business_only_fields(
    sample_context, monkeypatch
):
    from agent.util import message_util

    uuids = iter(
        [
            SimpleNamespace(hex="out_1"),
            SimpleNamespace(hex="idem_1"),
            SimpleNamespace(hex="trace_1"),
        ]
    )
    monkeypatch.setattr(message_util.uuid, "uuid4", lambda: next(uuids))
    sample_context["conversation"]["business_conversation_key"] = "bc_1"
    sample_context["conversation"]["conversation_info"]["chat_history"] = [
        {
            "metadata": {
                "causal_inbound_event_id": "in_1",
                "clawscale": {"conversation_id": "legacy_route_should_not_surface"},
            }
        }
    ]

    metadata = message_util.build_clawscale_push_metadata(
        str(sample_context["user"]["_id"]),
        now_ts=1710000000,
        context=sample_context,
    )

    assert metadata == {
        "business_conversation_key": "bc_1",
        "output_id": "out_1",
        "delivery_mode": "push",
        "idempotency_key": "idem_1",
        "trace_id": "trace_1",
        "causal_inbound_event_id": "in_1",
    }
