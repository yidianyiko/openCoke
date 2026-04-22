from types import SimpleNamespace
from unittest.mock import MagicMock


def _stub_prompt_formatter_dependencies(monkeypatch):
    from agent.util import message_util

    monkeypatch.setattr(
        message_util,
        "UserDAO",
        lambda: MagicMock(get_user_by_id=lambda _: None),
    )
    monkeypatch.setattr(
        message_util,
        "MongoDBBase",
        lambda: MagicMock(get_vector_by_id=lambda *_: None),
    )


def test_message_util_emits_business_only_output_doc_for_clawscale_proactive_message(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["message_source"] = "deferred_action"
    sample_context["system_message_metadata"] = {"kind": "proactive_followup"}
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

    assert message["account_id"] == sample_context["user"]["id"]
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


def test_clawscale_image_message_prompt_keeps_attachment_fallback(monkeypatch):
    from agent.util.message_util import messages_to_str

    _stub_prompt_formatter_dependencies(monkeypatch)

    rendered = messages_to_str(
        [
            {
                "platform": "business",
                "from_user": "acct_1",
                "input_timestamp": 1710000000,
                "message_type": "image",
                "message": "caption\n\nAttachment: https://cdn.example.com/photo.jpg",
                "metadata": {
                    "source": "clawscale",
                    "coke_account": {"id": "acct_1", "display_name": "Alice"},
                },
            }
        ]
    )

    assert "Attachment: https://cdn.example.com/photo.jpg" in rendered


def test_clawscale_voice_message_prompt_keeps_attachment_fallback(monkeypatch):
    from agent.util.message_util import messages_to_str

    _stub_prompt_formatter_dependencies(monkeypatch)

    rendered = messages_to_str(
        [
            {
                "platform": "business",
                "from_user": "acct_1",
                "input_timestamp": 1710000000,
                "message_type": "voice",
                "message": "Attachment: https://cdn.example.com/audio.ogg",
                "metadata": {
                    "source": "clawscale",
                    "coke_account": {"id": "acct_1", "display_name": "Alice"},
                },
            }
        ]
    )

    assert "Attachment: https://cdn.example.com/audio.ogg" in rendered


def test_clawscale_mixed_file_message_prompt_keeps_attachment_fallback(monkeypatch):
    from agent.util.message_util import messages_to_str

    _stub_prompt_formatter_dependencies(monkeypatch)

    rendered = messages_to_str(
        [
            {
                "platform": "business",
                "from_user": "acct_1",
                "input_timestamp": 1710000000,
                "message_type": "text",
                "message": (
                    "please review\n\n"
                    "Attachment: https://cdn.example.com/photo.jpg\n"
                    "Attachment: https://cdn.example.com/doc.pdf"
                ),
                "metadata": {
                    "source": "clawscale",
                    "coke_account": {"id": "acct_1", "display_name": "Alice"},
                },
            }
        ]
    )

    assert "Attachment: https://cdn.example.com/photo.jpg" in rendered
    assert "Attachment: https://cdn.example.com/doc.pdf" in rendered


def test_clawscale_redacted_inline_data_marker_prompt_keeps_attachment_fallback(
    monkeypatch,
):
    from agent.util.message_util import messages_to_str

    _stub_prompt_formatter_dependencies(monkeypatch)

    redacted_marker = "[inline image/png attachment: screenshot.png]"
    rendered = messages_to_str(
        [
            {
                "platform": "business",
                "from_user": "acct_1",
                "input_timestamp": 1710000000,
                "message_type": "image",
                "message": f"Attachment: {redacted_marker}",
                "metadata": {
                    "source": "clawscale",
                    "coke_account": {"id": "acct_1", "display_name": "Alice"},
                },
            }
        ]
    )

    assert f"Attachment: {redacted_marker}" in rendered
    assert "data:" not in rendered


def test_message_util_marks_proactive_output_failed_when_business_key_missing(
    sample_context, monkeypatch
):
    from agent.util import message_util

    now_ts = 1710000000
    sample_context["message_source"] = "deferred_action"
    sample_context["system_message_metadata"] = {"kind": "proactive_followup"}
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


def test_message_util_injects_business_key_into_clawscale_sync_reply_metadata(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["message_source"] = "user"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["platform"] = "business"
    sample_context["conversation"]["business_conversation_key"] = "bc_1"
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {
            "metadata": {
                "source": "clawscale",
                "business_protocol": {
                    "delivery_mode": "request_response",
                    "causal_inbound_event_id": "in_evt_1",
                    "sync_reply_token": "sync_tok_1",
                    "gateway_conversation_id": "gw_conv_1",
                },
            }
        }
    ]

    def fake_send_message(platform, from_user, to_user, chatroom_name, message, **kwargs):
        return {
            "message": message,
            "metadata": kwargs["metadata"],
        }

    monkeypatch.setattr(message_util, "send_message", fake_send_message)

    message = message_util.send_message_via_context(sample_context, "普通回复")

    assert message["metadata"] == {
        "source": "clawscale",
        "business_protocol": {
            "delivery_mode": "request_response",
            "causal_inbound_event_id": "in_evt_1",
            "sync_reply_token": "sync_tok_1",
            "gateway_conversation_id": "gw_conv_1",
            "business_conversation_key": "bc_1",
        },
    }


def test_message_util_merges_extra_clawscale_sync_outputs_into_first_reply(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["message_source"] = "user"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["platform"] = "business"
    sample_context["conversation"]["business_conversation_key"] = "bc_1"
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {
            "metadata": {
                "source": "clawscale",
                "business_protocol": {
                    "delivery_mode": "request_response",
                    "causal_inbound_event_id": "in_evt_1",
                    "gateway_conversation_id": "gw_conv_1",
                },
            }
        }
    ]

    fake_mongo_state = {
        "document": None,
        "queries": [],
        "updates": [],
    }

    class FakeMongo:
        def find_one(self, collection_name, query):
            fake_mongo_state["queries"].append((collection_name, query))
            document = fake_mongo_state["document"]
            if collection_name != "outputmessages" or document is None:
                return None
            if query != {"_id": "out_1", "status": "pending"}:
                return None
            return dict(document)

        def update_one(self, collection_name, query, update):
            fake_mongo_state["updates"].append((collection_name, query, update))
            if collection_name != "outputmessages":
                return 0
            document = fake_mongo_state["document"]
            if document is None or query != {"_id": "out_1", "status": "pending"}:
                return 0
            document["message"] = update["$set"]["message"]
            return 1

    monkeypatch.setattr(message_util, "MongoDBBase", lambda: FakeMongo())

    def fake_send_message(platform, from_user, to_user, chatroom_name, message, **kwargs):
        payload = {
            "_id": "out_1",
            "message": message,
            "status": kwargs["status"],
            "handled_timestamp": kwargs["handled_timestamp"],
            "metadata": kwargs["metadata"],
        }
        fake_mongo_state["document"] = dict(payload)
        return payload

    monkeypatch.setattr(message_util, "send_message", fake_send_message)

    first = message_util.send_message_via_context(sample_context, "第一条同步回复")
    second = message_util.send_message_via_context(sample_context, "第二条同步回复")

    assert first["status"] == "pending"
    assert second["status"] == "pending"
    assert second["_id"] == "out_1"
    assert second["message"] == "第一条同步回复\n第二条同步回复"
    assert second["metadata"]["business_protocol"] == {
        "delivery_mode": "request_response",
        "causal_inbound_event_id": "in_evt_1",
        "gateway_conversation_id": "gw_conv_1",
        "business_conversation_key": "bc_1",
    }
    assert "failure_reason" not in second["metadata"]
    assert fake_mongo_state["document"]["message"] == "第一条同步回复\n第二条同步回复"
    assert fake_mongo_state["queries"] == [
        ("outputmessages", {"_id": "out_1", "status": "pending"})
    ]
    assert fake_mongo_state["updates"] == [
        (
            "outputmessages",
            {"_id": "out_1", "status": "pending"},
            {"$set": {"message": "第一条同步回复\n第二条同步回复"}},
        )
    ]


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
    sample_context["causal_inbound_event_id"] = "in_1"
    sample_context["conversation"]["conversation_info"]["chat_history"] = [
        {
            "metadata": {
                "causal_inbound_event_id": "legacy_in_1",
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


def test_build_clawscale_push_metadata_does_not_fallback_to_legacy_route_ids(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["conversation"].pop("business_conversation_key", None)
    sample_context["conversation"]["_id"] = "legacy_conv_1"
    sample_context["conversation_id"] = "legacy_ctx_conv_1"
    sample_context["conversation"]["conversation_info"]["chat_history"] = [
        {"metadata": {"clawscale": {"conversation_id": "legacy_route_1"}}}
    ]

    uuid_calls = []
    monkeypatch.setattr(
        message_util.uuid,
        "uuid4",
        lambda: uuid_calls.append("called") or SimpleNamespace(hex="unused"),
    )

    metadata = message_util.build_clawscale_push_metadata(
        str(sample_context["user"]["_id"]),
        now_ts=1710000000,
        context=sample_context,
    )

    assert metadata == {}
    assert uuid_calls == []


def test_build_clawscale_push_metadata_does_not_treat_gateway_id_as_business_key(
    sample_context, monkeypatch
):
    from agent.util import message_util

    sample_context["conversation"].pop("business_conversation_key", None)
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {
            "metadata": {
                "source": "clawscale",
                "business_protocol": {
                    "delivery_mode": "request_response",
                    "gateway_conversation_id": "gw_conv_fallback_1",
                },
            }
        }
    ]
    uuid_calls = []
    monkeypatch.setattr(
        message_util.uuid,
        "uuid4",
        lambda: uuid_calls.append("called") or SimpleNamespace(hex="unused"),
    )

    metadata = message_util.build_clawscale_push_metadata(
        str(sample_context["user"]["_id"]),
        now_ts=1710000000,
        context=sample_context,
    )

    assert metadata == {}
    assert uuid_calls == []


def test_build_clawscale_push_metadata_does_not_inherit_historical_causal_event_id(
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
        {"metadata": {"causal_inbound_event_id": "legacy_in_1"}}
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
    }
