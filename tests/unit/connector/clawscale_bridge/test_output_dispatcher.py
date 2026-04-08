from unittest.mock import ANY, MagicMock


def test_output_dispatcher_claims_pending_message_before_sending(monkeypatch):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }

    mongo = MagicMock()
    mongo.get_collection.return_value = collection

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        session=MagicMock(),
        outbound_api_url="https://gateway.local/api/outbound",
    )
    dispatcher.session.post.return_value.status_code = 200

    handled = dispatcher.dispatch_once()

    assert handled is True
    collection.find_one_and_update.assert_called_once_with(
        {
            "platform": "wechat",
            "expect_output_timestamp": {"$lte": now},
            "metadata.route_via": "clawscale",
            "metadata.delivery_mode": "push",
            "$or": [
                {"status": "pending"},
                {
                    "status": "dispatching",
                    "$or": [
                        {
                            "dispatching_timestamp": {
                                "$lte": now
                                - output_dispatcher.STALE_DISPATCHING_TIMEOUT_SECONDS
                            }
                        },
                        {"dispatching_timestamp": {"$exists": False}},
                    ],
                },
            ],
        },
        {"$set": {"status": "dispatching", "dispatching_timestamp": now}},
        return_document=output_dispatcher.ReturnDocument.AFTER,
    )
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "handled", "handled_timestamp": now}},
    )


def test_output_dispatcher_posts_to_configured_outbound_url_with_api_key():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }
    mongo.get_collection.return_value = collection

    session = MagicMock()
    session.post.return_value.status_code = 200

    dispatcher = ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    dispatcher.dispatch_once()

    session.post.assert_called_once_with(
        "https://gateway.local/api/outbound",
        json={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "external_end_user_id": "wxid_123",
            "text": "记得开会",
            "idempotency_key": "push_1",
        },
        headers={"Authorization": "Bearer outbound-secret"},
        timeout=15,
    )


def test_output_dispatcher_marks_claimed_message_failed_when_post_raises(
    monkeypatch,
):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    session = MagicMock()
    session.post.side_effect = RuntimeError("temporary")

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    handled = dispatcher.dispatch_once()

    assert handled is False
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "failed", "handled_timestamp": now}},
    )


def test_output_dispatcher_marks_malformed_claimed_message_failed(monkeypatch):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    session = MagicMock()

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    handled = dispatcher.dispatch_once()

    assert handled is False
    session.post.assert_not_called()
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "failed", "handled_timestamp": now}},
    )


def test_output_dispatcher_treats_duplicate_request_409_as_handled():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }
    mongo.get_collection.return_value = collection

    session = MagicMock()
    session.post.return_value.status_code = 409
    session.post.return_value.json.return_value = {"error": "duplicate_request"}

    dispatcher = ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "handled", "handled_timestamp": ANY}},
    )


def test_output_dispatcher_releases_in_progress_duplicate_for_retry():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }
    mongo.get_collection.return_value = collection

    session = MagicMock()
    session.post.return_value.status_code = 409
    session.post.return_value.json.return_value = {"error": "duplicate_request_in_progress"}

    dispatcher = ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    handled = dispatcher.dispatch_once()

    assert handled is False
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "pending"}, "$unset": {"dispatching_timestamp": ""}},
    )


def test_output_dispatcher_marks_conflicting_duplicate_failed():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }
    mongo.get_collection.return_value = collection

    session = MagicMock()
    session.post.return_value.status_code = 409
    session.post.return_value.json.return_value = {"error": "idempotency_key_conflict"}

    dispatcher = ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    handled = dispatcher.dispatch_once()

    assert handled is False
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "failed", "handled_timestamp": ANY}},
    )


def test_output_dispatcher_reclaims_stale_dispatching_message(monkeypatch):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = {
        "_id": "out_2",
        "platform": "wechat",
        "status": "dispatching",
        "dispatching_timestamp": now,
        "message": "稍后联系",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_2",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_456",
            "push_idempotency_key": "push_2",
        },
    }

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    session = MagicMock()
    session.post.return_value.status_code = 200

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    collection.find_one_and_update.assert_called_once_with(
        {
            "platform": "wechat",
            "expect_output_timestamp": {"$lte": now},
            "metadata.route_via": "clawscale",
            "metadata.delivery_mode": "push",
            "$or": [
                {"status": "pending"},
                {
                    "status": "dispatching",
                    "$or": [
                        {
                            "dispatching_timestamp": {
                                "$lte": now
                                - output_dispatcher.STALE_DISPATCHING_TIMEOUT_SECONDS
                            }
                        },
                        {"dispatching_timestamp": {"$exists": False}},
                    ],
                },
            ],
        },
        {"$set": {"status": "dispatching", "dispatching_timestamp": now}},
        return_document=output_dispatcher.ReturnDocument.AFTER,
    )
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_2", "status": "dispatching"},
        {"$set": {"status": "handled", "handled_timestamp": now}},
    )
