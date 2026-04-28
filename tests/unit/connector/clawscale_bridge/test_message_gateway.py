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
            "coke_account_id": "acct_1",
            "coke_account_display_name": "Alice",
            "account_status": "subscription_required",
            "email_verified": True,
            "subscription_active": False,
            "subscription_expires_at": "2026-04-30T00:00:00Z",
            "account_access_allowed": False,
            "account_access_denied_reason": "subscription_required",
            "renewal_url": "https://renew.example/checkout",
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
    assert doc["metadata"]["customer"] == {
        "id": "acct_1",
        "display_name": "Alice",
    }
    assert doc["metadata"]["coke_account"] == {
        "id": "acct_1",
        "display_name": "Alice",
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


def test_message_gateway_builds_business_protocol_with_optional_gateway_metadata():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())
    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        causal_inbound_event_id="in_evt_2",
        inbound={
            "timestamp": 1710000000,
            "business_conversation_key": "conv_key_2",
        },
    )

    assert list(doc["metadata"]["business_protocol"]) == [
        "delivery_mode",
        "causal_inbound_event_id",
        "business_conversation_key",
    ]
    assert doc["metadata"]["business_protocol"] == {
        "delivery_mode": "request_response",
        "causal_inbound_event_id": "in_evt_2",
        "business_conversation_key": "conv_key_2",
    }


def test_message_gateway_preserves_single_image_attachment_metadata_and_type():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    attachment = {
        "url": "https://cdn.example.com/photo.jpg",
        "contentType": "image/jpeg",
        "filename": "photo.jpg",
        "safeDisplayUrl": "https://cdn.example.com/photo.jpg",
        "size": 1234,
    }
    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())

    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="caption\n\nAttachment: https://cdn.example.com/photo.jpg",
        causal_inbound_event_id="in_evt_image_1",
        inbound={
            "timestamp": 1710000000,
            "inbound_text": "caption",
            "attachments": [attachment],
        },
    )

    assert doc["message_type"] == "image"
    assert doc["metadata"]["attachments"] == [attachment]
    assert doc["metadata"]["mediaUrls"] == ["https://cdn.example.com/photo.jpg"]
    assert doc["metadata"]["inbound_text"] == "caption"


def test_message_gateway_preserves_single_audio_attachment_metadata_and_type():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    attachment = {
        "url": "https://cdn.example.com/audio.ogg",
        "contentType": "audio/ogg",
        "filename": "audio.ogg",
        "safeDisplayUrl": "https://cdn.example.com/audio.ogg",
    }
    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())

    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="Attachment: https://cdn.example.com/audio.ogg",
        causal_inbound_event_id="in_evt_audio_1",
        inbound={
            "timestamp": 1710000000,
            "inbound_text": "",
            "attachments": [attachment],
        },
    )

    assert doc["message_type"] == "voice"
    assert doc["metadata"]["attachments"] == [attachment]
    assert doc["metadata"]["mediaUrls"] == ["https://cdn.example.com/audio.ogg"]
    assert doc["metadata"]["inbound_text"] == ""


def test_message_gateway_keeps_mixed_and_file_attachments_as_text():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    attachments = [
        {
            "url": "https://cdn.example.com/photo.jpg",
            "contentType": "image/jpeg",
            "filename": "photo.jpg",
            "safeDisplayUrl": "https://cdn.example.com/photo.jpg",
        },
        {
            "url": "https://cdn.example.com/doc.pdf",
            "contentType": "application/pdf",
            "filename": "doc.pdf",
            "safeDisplayUrl": "https://cdn.example.com/doc.pdf",
        },
    ]
    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())

    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text=(
            "please review\n\n"
            "Attachment: https://cdn.example.com/photo.jpg\n"
            "Attachment: https://cdn.example.com/doc.pdf"
        ),
        causal_inbound_event_id="in_evt_mixed_1",
        inbound={
            "timestamp": 1710000000,
            "inbound_text": "please review",
            "attachments": attachments,
        },
    )

    assert doc["message_type"] == "text"
    assert doc["metadata"]["attachments"] == attachments
    assert doc["metadata"]["mediaUrls"] == [
        "https://cdn.example.com/photo.jpg",
        "https://cdn.example.com/doc.pdf",
    ]
    assert doc["metadata"]["inbound_text"] == "please review"


def test_message_gateway_preserves_redacted_inline_attachment_values():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    attachment = {
        "url": "[inline image/png attachment: screenshot.png]",
        "contentType": "image/png",
        "filename": "screenshot.png",
        "safeDisplayUrl": "[inline image/png attachment: screenshot.png]",
    }
    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())

    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="Attachment: [inline image/png attachment: screenshot.png]",
        causal_inbound_event_id="in_evt_inline_1",
        inbound={
            "timestamp": 1710000000,
            "inbound_text": "",
            "attachments": [attachment],
        },
    )

    assert doc["message_type"] == "image"
    assert doc["metadata"]["attachments"] == [attachment]
    assert doc["metadata"]["mediaUrls"] == [
        "[inline image/png attachment: screenshot.png]"
    ]
    assert not doc["metadata"]["mediaUrls"][0].startswith("data:")


def test_message_gateway_redacts_raw_data_url_attachments_before_persistence():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    raw_payload = "cG5n"
    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())

    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="Attachment: raw upload",
        causal_inbound_event_id="in_evt_raw_data_1",
        inbound={
            "timestamp": 1710000000,
            "inbound_text": "",
            "attachments": [
                {
                    "url": f"\x00\x1fdata:image/png;base64,{raw_payload}",
                    "contentType": "image/png",
                    "filename": "screenshot.png",
                    "safeDisplayUrl": "data:image/png;base64,unsafe-display",
                    "extra": "must not persist",
                }
            ],
        },
    )

    assert doc["message_type"] == "image"
    assert doc["metadata"]["attachments"] == [
        {
            "url": "[redacted inline image/png attachment]",
            "contentType": "image/png",
            "filename": "screenshot.png",
            "safeDisplayUrl": "[redacted inline image/png attachment]",
        }
    ]
    assert doc["metadata"]["mediaUrls"] == ["[redacted inline image/png attachment]"]
    assert "data:image" not in str(doc)
    assert raw_payload not in str(doc)


def test_message_gateway_copies_attachments_before_persistence():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    attachment = {
        "url": "https://cdn.example.com/photo.jpg",
        "contentType": "image/jpeg",
        "filename": "photo.jpg",
        "safeDisplayUrl": "https://cdn.example.com/photo.jpg",
    }
    inbound = {
        "timestamp": 1710000000,
        "inbound_text": "caption",
        "attachments": [attachment],
    }
    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())

    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="caption\n\nAttachment: https://cdn.example.com/photo.jpg",
        causal_inbound_event_id="in_evt_alias_1",
        inbound=inbound,
    )

    attachment["url"] = "data:image/png;base64,cG5n"
    attachment["filename"] = "mutated.png"
    attachment["extra"] = "mutated"
    inbound["attachments"].append(
        {
            "url": "https://cdn.example.com/other.jpg",
            "contentType": "image/jpeg",
        }
    )

    assert doc["metadata"]["attachments"] == [
        {
            "url": "https://cdn.example.com/photo.jpg",
            "contentType": "image/jpeg",
            "filename": "photo.jpg",
            "safeDisplayUrl": "https://cdn.example.com/photo.jpg",
        }
    ]
    assert doc["metadata"]["mediaUrls"] == ["https://cdn.example.com/photo.jpg"]


def test_message_gateway_drops_malformed_attachment_without_url():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())

    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="looks like an image",
        causal_inbound_event_id="in_evt_malformed_1",
        inbound={
            "timestamp": 1710000000,
            "attachments": [
                {
                    "contentType": "image/png",
                    "filename": "missing-url.png",
                }
            ],
        },
    )

    assert doc["message_type"] == "text"
    assert "attachments" not in doc["metadata"]
    assert "mediaUrls" not in doc["metadata"]


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


def test_message_gateway_enqueue_strips_retired_auth_only_fields_from_emitted_payload():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    mongo = MagicMock()
    collection = MagicMock()
    mongo.get_collection.return_value = collection
    gateway = CokeMessageGateway(mongo=mongo, user_dao=MagicMock())

    gateway.enqueue(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        inbound={
            "timestamp": 1710000000,
            "inbound_event_id": "in_evt_gateway_2",
            "coke_account_id": "acct_1",
            "coke_account_display_name": "Alice",
            "account_status": "subscription_required",
            "email_verified": True,
            "subscription_active": False,
            "subscription_expires_at": "2026-04-30T00:00:00Z",
            "account_access_allowed": False,
            "account_access_denied_reason": "subscription_required",
            "renewal_url": "https://renew.example/checkout",
        },
    )

    inserted = collection.update_one.call_args.args[1]["$setOnInsert"]
    customer = inserted["metadata"]["customer"]
    coke_account = inserted["metadata"]["coke_account"]
    forbidden_keys = {
        "account_status",
        "email_verified",
        "subscription_active",
        "subscription_expires_at",
        "account_access_allowed",
        "account_access_denied_reason",
        "renewal_url",
    }

    assert set(customer) == {"id", "display_name"}
    assert set(coke_account) == {"id", "display_name"}
    assert forbidden_keys.isdisjoint(customer)
    assert forbidden_keys.isdisjoint(coke_account)
