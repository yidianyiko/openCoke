from unittest.mock import MagicMock


def test_reply_waiter_consumes_first_pending_text_reply_by_causal_inbound_event():
    from connector.clawscale_bridge.reply_waiter import ReplyWaiter

    mongo = MagicMock()
    mongo.find_one.side_effect = [
        None,
        {
            "_id": "out_1",
            "status": "pending",
            "message_type": "text",
            "message": "收到",
            "metadata": {
                "source": "clawscale",
                "business_protocol": {
                    "delivery_mode": "request_response",
                    "causal_inbound_event_id": "in_evt_1",
                    "sync_reply_token": "sync_tok_1",
                    "business_conversation_key": "conv_key_1",
                },
            },
        },
    ]

    waiter = ReplyWaiter(mongo=mongo, poll_interval_seconds=0.01, timeout_seconds=1)
    reply = waiter.wait_for_reply("in_evt_1", sync_reply_token="sync_tok_1")

    assert reply == {
        "reply": "收到",
        "output_id": "out_1",
        "causal_inbound_event_id": "in_evt_1",
        "business_conversation_key": "conv_key_1",
    }
    mongo.find_one.assert_called_with(
        "outputmessages",
        {
            "status": "pending",
            "message_type": "text",
            "metadata.source": "clawscale",
            "metadata.business_protocol.delivery_mode": "request_response",
            "metadata.business_protocol.causal_inbound_event_id": "in_evt_1",
            "metadata.business_protocol.sync_reply_token": "sync_tok_1",
        },
    )
    mongo.update_one.assert_called_once()


def test_reply_waiter_allows_matching_without_sync_reply_token():
    from connector.clawscale_bridge.reply_waiter import ReplyWaiter

    mongo = MagicMock()
    mongo.find_one.return_value = {
        "_id": "out_2",
        "status": "pending",
        "message_type": "text",
        "message": "已收到",
        "metadata": {
            "source": "clawscale",
            "business_protocol": {
                "delivery_mode": "request_response",
                "causal_inbound_event_id": "in_evt_2",
            },
        },
    }

    waiter = ReplyWaiter(mongo=mongo, poll_interval_seconds=0.01, timeout_seconds=1)
    reply = waiter.wait_for_reply("in_evt_2")

    assert reply == {
        "reply": "已收到",
        "output_id": "out_2",
        "causal_inbound_event_id": "in_evt_2",
    }
    query = mongo.find_one.call_args.args[1]
    assert "metadata.business_protocol.sync_reply_token" not in query


def test_reply_waiter_can_peek_pending_reply_without_marking_it_handled():
    from connector.clawscale_bridge.reply_waiter import ReplyWaiter

    mongo = MagicMock()
    mongo.find_one.return_value = {
        "_id": "out_3",
        "status": "pending",
        "message_type": "text",
        "message": "稍后送达",
        "metadata": {
            "source": "clawscale",
            "business_protocol": {
                "delivery_mode": "request_response",
                "causal_inbound_event_id": "in_evt_3",
                "business_conversation_key": "conv_key_3",
            },
        },
    }

    waiter = ReplyWaiter(mongo=mongo, poll_interval_seconds=0.01, timeout_seconds=1)
    message = waiter.wait_for_reply_message("in_evt_3", consume=False)

    assert message == {
        "_id": "out_3",
        "status": "pending",
        "message_type": "text",
        "message": "稍后送达",
        "metadata": {
            "source": "clawscale",
            "business_protocol": {
                "delivery_mode": "request_response",
                "causal_inbound_event_id": "in_evt_3",
                "business_conversation_key": "conv_key_3",
            },
        },
    }
    mongo.update_one.assert_not_called()
