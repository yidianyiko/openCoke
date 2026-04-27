from unittest.mock import ANY, MagicMock

import pytest


def _build_message_doc(**overrides):
    doc = {
        "_id": "out_1",
        "account_id": "acc_1",
        "status": "pending",
        "message": "记得开会",
        "message_type": "text",
        "expect_output_timestamp": 1710000000,
        "metadata": {
            "business_conversation_key": "bc_1",
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "output_id": "out_1",
        },
    }
    doc.update(overrides)
    return doc


def test_output_dispatcher_claims_pending_message_before_sending_and_posts_to_gateway(
    monkeypatch,
):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching"
    )

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    collection.find_one_and_update.assert_called_once_with(
        {
            "$and": [
                {
                    "$or": [
                        {"customer_id": {"$exists": True}},
                        {"account_id": {"$exists": True}},
                    ]
                }
            ],
            "expect_output_timestamp": {"$lte": now},
            "metadata.business_conversation_key": {"$exists": True},
            "metadata.delivery_mode": "push",
            "metadata.output_id": {"$exists": True},
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
    gateway_client.post_output.assert_called_once_with(
        output_id="out_1",
        customer_id="acc_1",
        business_conversation_key="bc_1",
        text="记得开会",
        message_type="text",
        delivery_mode="push",
        expect_output_timestamp=1710000000,
        idempotency_key="idem_1",
        trace_id="trace_1",
        causal_inbound_event_id=None,
        media_urls=None,
        audio_as_voice=False,
    )
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "handled", "handled_timestamp": now}},
    )


def test_output_dispatcher_marks_claimed_message_failed_when_post_raises(monkeypatch):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching"
    )

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.side_effect = RuntimeError("temporary")

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
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
        "account_id": "acc_1",
        "status": "dispatching",
        "message": "记得开会",
        "metadata": {
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "output_id": "out_1",
        },
    }

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    handled = dispatcher.dispatch_once()

    assert handled is False
    gateway_client.post_output.assert_not_called()
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "failed", "handled_timestamp": now}},
    )


def test_output_dispatcher_forwards_trimmed_image_url(monkeypatch):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching",
        message_type="image",
        metadata={
            "business_conversation_key": "bc_1",
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "output_id": "out_1",
            "url": "  https://cdn.example.com/image.png  ",
        },
    )

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    gateway_client.post_output.assert_called_once_with(
        output_id="out_1",
        customer_id="acc_1",
        business_conversation_key="bc_1",
        text="记得开会",
        message_type="image",
        delivery_mode="push",
        expect_output_timestamp=1710000000,
        idempotency_key="idem_1",
        trace_id="trace_1",
        causal_inbound_event_id=None,
        media_urls=["https://cdn.example.com/image.png"],
        audio_as_voice=False,
    )


def test_output_dispatcher_forwards_voice_url_as_voice(monkeypatch):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching",
        message_type="voice",
        metadata={
            "business_conversation_key": "bc_1",
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "output_id": "out_1",
            "url": "https://cdn.example.com/voice.mp3",
        },
    )

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    gateway_client.post_output.assert_called_once_with(
        output_id="out_1",
        customer_id="acc_1",
        business_conversation_key="bc_1",
        text="记得开会",
        message_type="voice",
        delivery_mode="push",
        expect_output_timestamp=1710000000,
        idempotency_key="idem_1",
        trace_id="trace_1",
        causal_inbound_event_id=None,
        media_urls=["https://cdn.example.com/voice.mp3"],
        audio_as_voice=True,
    )


@pytest.mark.parametrize(
    ("message_type", "metadata_url"),
    [
        ("image", "   "),
        ("voice", None),
    ],
)
def test_output_dispatcher_marks_malformed_media_message_failed(
    monkeypatch,
    message_type,
    metadata_url,
):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    metadata = {
        "business_conversation_key": "bc_1",
        "delivery_mode": "push",
        "idempotency_key": "idem_1",
        "trace_id": "trace_1",
        "output_id": "out_1",
    }
    if metadata_url is not None:
        metadata["url"] = metadata_url

    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching",
        message_type=message_type,
        metadata=metadata,
    )

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    handled = dispatcher.dispatch_once()

    assert handled is False
    gateway_client.post_output.assert_not_called()
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "failed", "handled_timestamp": now}},
    )


def test_output_dispatcher_treats_duplicate_request_409_as_handled():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching"
    )
    mongo.get_collection.return_value = collection

    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 409
    gateway_client.post_output.return_value.json.return_value = {
        "error": "duplicate_request"
    }

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, gateway_client=gateway_client)

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
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching"
    )
    mongo.get_collection.return_value = collection

    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 409
    gateway_client.post_output.return_value.json.return_value = {"error": "duplicate"}

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, gateway_client=gateway_client)

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
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching"
    )
    mongo.get_collection.return_value = collection

    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 409
    gateway_client.post_output.return_value.json.return_value = {
        "error": "idempotency_key_conflict"
    }

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, gateway_client=gateway_client)

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
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching",
        dispatching_timestamp=now - output_dispatcher.STALE_DISPATCHING_TIMEOUT_SECONDS - 1,
    )

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    collection.find_one_and_update.assert_called_once()


def test_output_dispatcher_claims_customer_id_messages_during_compatibility_window(
    monkeypatch,
):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    now = 1710000000
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: now)

    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        account_id=None,
        customer_id="ck_123",
        status="dispatching",
    )

    mongo = MagicMock()
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    handled = dispatcher.dispatch_once()

    assert handled is True
    collection.find_one_and_update.assert_called_once_with(
        {
            "$and": [
                {
                    "$or": [
                        {"customer_id": {"$exists": True}},
                        {"account_id": {"$exists": True}},
                    ]
                }
            ],
            "expect_output_timestamp": {"$lte": now},
            "metadata.business_conversation_key": {"$exists": True},
            "metadata.delivery_mode": "push",
            "metadata.output_id": {"$exists": True},
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
    gateway_client.post_output.assert_called_once_with(
        output_id="out_1",
        customer_id="ck_123",
        business_conversation_key="bc_1",
        text="记得开会",
        message_type="text",
        delivery_mode="push",
        expect_output_timestamp=1710000000,
        idempotency_key="idem_1",
        trace_id="trace_1",
        causal_inbound_event_id=None,
        media_urls=None,
        audio_as_voice=False,
    )
