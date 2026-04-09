from unittest.mock import MagicMock

from pymongo.errors import DuplicateKeyError


def test_message_gateway_builds_normalized_business_protocol_input_message():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())
    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        causal_inbound_event_id="in_evt_1",
        inbound={
            "timestamp": 1710000000,
            "sync_reply_token": "sync_tok_1",
            "business_conversation_key": "conv_key_1",
            "gateway_conversation_id": "gw_conv_1",
        },
    )

    assert doc["from_user"] == "user_1"
    assert doc["to_user"] == "char_1"
    assert doc["metadata"]["source"] == "clawscale"
    assert doc["metadata"]["business_protocol"] == {
        "delivery_mode": "request_response",
        "causal_inbound_event_id": "in_evt_1",
        "sync_reply_token": "sync_tok_1",
        "business_conversation_key": "conv_key_1",
        "gateway_conversation_id": "gw_conv_1",
    }
    assert "bridge_request_id" not in doc["metadata"]
    assert "clawscale" not in doc["metadata"]


def test_message_gateway_enqueue_respects_inbound_event_id_without_minting():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    mongo = MagicMock()
    collection = MagicMock()
    mongo.get_collection.return_value = collection
    gateway = CokeMessageGateway(mongo=mongo, user_dao=MagicMock())

    causal_id = gateway.enqueue(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        inbound={
            "timestamp": 1710000000,
            "inbound_event_id": "in_evt_gateway_1",
        },
    )

    assert causal_id == "in_evt_gateway_1"
    collection.create_index.assert_called_once()
    collection.update_one.assert_called_once()
    inserted = collection.update_one.call_args.args[1]["$setOnInsert"]
    assert inserted["platform"] == "business"
    assert (
        inserted["metadata"]["business_protocol"]["causal_inbound_event_id"]
        == "in_evt_gateway_1"
    )
    assert "business_conversation_key" not in inserted["metadata"]["business_protocol"]


def test_message_gateway_enqueue_deduplicates_same_inbound_event_id():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    mongo = MagicMock()
    collection = MagicMock()
    mongo.get_collection.return_value = collection
    gateway = CokeMessageGateway(mongo=mongo, user_dao=MagicMock())

    first_id = gateway.enqueue(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        inbound={
            "timestamp": 1710000000,
            "inbound_event_id": "in_evt_dup_1",
        },
    )
    second_id = gateway.enqueue(
        account_id="user_1",
        character_id="char_1",
        text="你好(重试)",
        inbound={
            "timestamp": 1710000010,
            "inbound_event_id": "in_evt_dup_1",
        },
    )

    assert first_id == "in_evt_dup_1"
    assert second_id == "in_evt_dup_1"
    assert collection.update_one.call_count == 2
    mongo.find_one.assert_not_called()
    mongo.insert_one.assert_not_called()


def test_message_gateway_enqueue_returns_same_id_on_duplicate_key_race():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    mongo = MagicMock()
    collection = MagicMock()
    collection.update_one.side_effect = DuplicateKeyError("dup key")
    mongo.get_collection.return_value = collection
    gateway = CokeMessageGateway(mongo=mongo, user_dao=MagicMock())

    causal_id = gateway.enqueue(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        inbound={
            "timestamp": 1710000000,
            "inbound_event_id": "in_evt_race_1",
        },
    )

    assert causal_id == "in_evt_race_1"
