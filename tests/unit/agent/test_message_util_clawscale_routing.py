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


def test_message_util_marks_proactive_output_failed_when_clawscale_route_missing(
    monkeypatch, sample_context
):
    from agent.util import message_util

    now_ts = 1710000000
    sample_context["message_source"] = "future"
    sample_context["conversation_id"] = "conv_missing_route"
    sample_context["conversation"]["platform"] = "wechat"
    sample_context["conversation"]["chatroom_name"] = None
    sample_context["conversation"]["conversation_info"]["input_messages"] = []

    logged_messages = []

    def fake_warning(msg, *args, **kwargs):
        logged_messages.append(msg % args if args else msg)

    monkeypatch.setattr(
        message_util, "build_clawscale_push_metadata", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(message_util.time, "time", lambda: now_ts)
    monkeypatch.setattr(message_util.logger, "warning", fake_warning)
    monkeypatch.setattr(
        message_util,
        "send_message",
        lambda platform, from_user, to_user, chatroom_name, message, **kwargs: {
            "platform": platform,
            "from_user": from_user,
            "to_user": to_user,
            "chatroom_name": chatroom_name,
            "message": message,
            "status": kwargs["status"],
            "handled_timestamp": kwargs["handled_timestamp"],
            "metadata": kwargs["metadata"],
        },
    )

    message = message_util.send_message_via_context(
        sample_context,
        "提醒你喝水",
        expect_output_timestamp=now_ts + 3600,
    )

    assert message["status"] == "failed"
    assert message["handled_timestamp"] == now_ts
    assert message["metadata"]["failure_reason"] == "missing_clawscale_push_route"
    assert message["metadata"]["route_via"] == "clawscale"
    assert message["metadata"]["delivery_mode"] == "push"
    assert any(
        "missing_clawscale_push_route" in log_message
        for log_message in logged_messages
    )
    assert any("wechat_personal" in log_message for log_message in logged_messages)


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


def test_clawscale_personal_inbound_creates_route_and_dispatches_proactive_output(
    monkeypatch,
):
    from agent.util import message_util
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher
    from connector.clawscale_bridge.identity_service import IdentityService
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    now_ts = 1710000000
    route_store = {}

    class FakePushRouteDAO:
        def __init__(self, *args, **kwargs):
            pass

        def upsert_route(self, **kwargs):
            route_store.clear()
            route_store.update(kwargs)

        def find_route_for_conversation(self, account_id, conversation_id, platform):
            if (
                route_store.get("account_id") == account_id
                and route_store.get("conversation_id") == conversation_id
                and route_store.get("platform") == platform
            ):
                return {
                    "tenant_id": route_store["tenant_id"],
                    "channel_id": route_store["channel_id"],
                    "platform": route_store["platform"],
                    "external_end_user_id": route_store["external_end_user_id"],
                }
            return None

        def find_latest_route_for_account(self, account_id, platform):
            if (
                route_store.get("account_id") == account_id
                and route_store.get("platform") == platform
            ):
                return {
                    "tenant_id": route_store["tenant_id"],
                    "channel_id": route_store["channel_id"],
                    "platform": route_store["platform"],
                    "external_end_user_id": route_store["external_end_user_id"],
                }
            return None

    class FakeExternalIdentityDAO:
        def __init__(self, *args, **kwargs):
            pass

        def find_primary_push_target(self, account_id, source):
            raise AssertionError(
                f"expected clawscale push route lookup for {account_id=} {source=}"
            )

    class FakeMongoCollection:
        def __init__(self, message):
            self.message = message

        def find_one_and_update(self, query, update, return_document=None):
            assert query == {
                "platform": "wechat",
                "expect_output_timestamp": {"$lte": now_ts},
                "metadata.route_via": "clawscale",
                "metadata.delivery_mode": "push",
                "$or": [
                    {"status": "pending"},
                    {
                        "status": "dispatching",
                        "$or": [
                            {
                                "dispatching_timestamp": {
                                    "$lte": now_ts
                                    - output_dispatcher.STALE_DISPATCHING_TIMEOUT_SECONDS
                                }
                            },
                            {"dispatching_timestamp": {"$exists": False}},
                        ],
                    },
                ],
            }
            assert update == {
                "$set": {"status": "dispatching", "dispatching_timestamp": now_ts}
            }
            assert return_document == output_dispatcher.ReturnDocument.AFTER
            return self.message

    class FakeMongo:
        def __init__(self, message):
            self.collection = FakeMongoCollection(message)
            self.updated = []

        def get_collection(self, name):
            assert name == "outputmessages"
            return self.collection

        def update_one(self, collection_name, filter_query, update):
            assert collection_name == "outputmessages"
            assert filter_query == {"_id": "out_1", "status": "dispatching"}
            assert update == {
                "$set": {"status": "handled", "handled_timestamp": now_ts}
            }
            self.updated.append((collection_name, filter_query, update))

    monkeypatch.setattr(
        "dao.clawscale_push_route_dao.ClawscalePushRouteDAO",
        FakePushRouteDAO,
    )
    monkeypatch.setattr(
        "dao.external_identity_dao.ExternalIdentityDAO",
        FakeExternalIdentityDAO,
    )
    monkeypatch.setattr("connector.clawscale_bridge.identity_service.time.time", lambda: now_ts)
    monkeypatch.setattr("agent.util.message_util.time.time", lambda: now_ts)
    monkeypatch.setattr(
        "connector.clawscale_bridge.output_dispatcher.time.time",
        lambda: now_ts,
    )

    identity_service = IdentityService(
        external_identity_dao=FakeExternalIdentityDAO(),
        binding_ticket_dao=object(),
        bind_session_service=object(),
        message_gateway=type(
            "FakeGateway",
            (),
            {
                "enqueue": lambda self, **kwargs: "req_1",
            },
        )(),
        reply_waiter=type(
            "FakeReplyWaiter",
            (),
            {
                "wait_for_reply": lambda self, request_id: "personal ownership reply",
            },
        )(),
        bind_base_url="https://coke.local",
        target_character_id="char_1",
        push_route_dao=FakePushRouteDAO(),
    )

    inbound_result = identity_service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "channelScope": "personal",
                "clawscaleUserId": "csu_1",
                "cokeAccountId": "acct_1",
            },
        }
    )

    assert inbound_result == {"status": "ok", "reply": "personal ownership reply"}
    assert route_store == {
        "account_id": "acct_1",
        "tenant_id": "ten_1",
        "channel_id": "ch_1",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_123",
        "conversation_id": "conv_1",
        "now_ts": now_ts,
        "clawscale_user_id": "csu_1",
    }

    sent_messages = []

    def fake_send_message(platform, from_user, to_user, chatroom_name, message, **kwargs):
        output_message = {
            "_id": "out_1",
            "platform": platform,
            "status": kwargs.get("status", "pending"),
            "expect_output_timestamp": kwargs.get("expect_output_timestamp")
            or now_ts,
            "handled_timestamp": kwargs.get("expect_output_timestamp") or now_ts,
            "from_user": from_user,
            "to_user": to_user,
            "chatroom_name": chatroom_name,
            "message_type": kwargs.get("message_type", "text"),
            "message": message,
            "metadata": kwargs["metadata"],
        }
        sent_messages.append(output_message)
        return output_message

    monkeypatch.setattr(message_util, "send_message", fake_send_message)

    proactive_context = {
        "message_source": "future",
        "user": {"_id": "acct_1"},
        "character": {"_id": "char_1"},
        "conversation_id": "conv_1",
        "conversation": {
            "_id": "conv_1",
            "platform": "wechat",
            "chatroom_name": None,
            "conversation_info": {"input_messages": []},
        },
    }

    proactive_message = message_util.send_message_via_context(
        proactive_context,
        "记得喝水",
    )

    assert proactive_message["metadata"]["route_via"] == "clawscale"
    assert proactive_message["metadata"]["delivery_mode"] == "push"
    assert proactive_message["metadata"]["tenant_id"] == "ten_1"
    assert proactive_message["metadata"]["channel_id"] == "ch_1"
    assert proactive_message["metadata"]["platform"] == "wechat_personal"
    assert proactive_message["metadata"]["external_end_user_id"] == "wxid_123"
    assert sent_messages[0]["metadata"]["push_idempotency_key"]

    mongo = FakeMongo(proactive_message)
    session = type(
        "FakeSession",
        (),
        {
            "post_calls": [],
            "post": lambda self, *args, **kwargs: self.post_calls.append((args, kwargs))
            or type("FakeResponse", (), {"status_code": 200})(),
        },
    )()

    dispatcher = ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    assert mongo.updated == [
        (
            "outputmessages",
            {"_id": "out_1", "status": "dispatching"},
            {"$set": {"status": "handled", "handled_timestamp": now_ts}},
        )
    ]
    assert session.post_calls == [
        (
            ("https://gateway.local/api/outbound",),
            {
                "json": {
                    "tenant_id": "ten_1",
                    "channel_id": "ch_1",
                    "external_end_user_id": "wxid_123",
                    "text": "记得喝水",
                    "idempotency_key": proactive_message["metadata"][
                        "push_idempotency_key"
                    ],
                },
                "headers": {"Authorization": "Bearer outbound-secret"},
                "timeout": 15,
            },
        )
    ]
