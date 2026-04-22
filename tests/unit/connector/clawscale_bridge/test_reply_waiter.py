from unittest.mock import MagicMock


class _ReplyWaiterMongo:
    def __init__(self, messages):
        self.messages = messages
        self.updates = []

    def find_one(self, collection_name, query):
        assert collection_name == "outputmessages"
        for message in self.messages:
            if _matches_query(message, query):
                return message
        return None

    def find_many(self, collection_name, query, limit=0):
        assert collection_name == "outputmessages"
        results = [
            message for message in self.messages if _matches_query(message, query)
        ]
        return results[:limit] if limit else results

    def update_one(self, collection_name, query, update):
        assert collection_name == "outputmessages"
        self.updates.append((query, update))
        for message in self.messages:
            if message["_id"] == query.get("_id") and message["status"] == query.get(
                "status"
            ):
                message.update(update.get("$set", {}))
                return 1
        return 0


def _matches_query(message, query):
    for key, expected in query.items():
        current = message
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        if current != expected:
            return False
    return True


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
        {
            "_id": "out_1",
            "status": "pending",
            "message_type": "text",
            "message": "收到\n后续补充",
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
        "reply": "收到\n后续补充",
        "output_id": "out_1",
        "causal_inbound_event_id": "in_evt_1",
        "business_conversation_key": "conv_key_1",
    }
    assert mongo.find_one.call_args_list[-1].args == (
        "outputmessages",
        {
            "_id": "out_1",
            "status": "pending",
        },
    )
    assert mongo.find_one.call_args_list[0].args == (
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
    assert mongo.find_one.call_args_list[1].args == (
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


def test_reply_waiter_merges_all_pending_text_replies_for_same_sync_event():
    from connector.clawscale_bridge.reply_waiter import ReplyWaiter

    mongo = _ReplyWaiterMongo(
        [
            {
                "_id": "out_2",
                "status": "pending",
                "message_type": "text",
                "message": "登录或验证邮箱后，点击授权",
                "expect_output_timestamp": 1710000005,
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "causal_inbound_event_id": "in_evt_multi",
                        "sync_reply_token": "sync_tok_multi",
                        "business_conversation_key": "conv_key_multi",
                    },
                },
            },
            {
                "_id": "out_1",
                "status": "pending",
                "message_type": "text",
                "message": "可以，打开这个入口：https://example.test/import",
                "expect_output_timestamp": 1710000000,
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "causal_inbound_event_id": "in_evt_multi",
                        "sync_reply_token": "sync_tok_multi",
                        "business_conversation_key": "conv_key_multi",
                    },
                },
            },
        ]
    )

    waiter = ReplyWaiter(mongo=mongo, poll_interval_seconds=0.01, timeout_seconds=1)
    reply = waiter.wait_for_reply("in_evt_multi", sync_reply_token="sync_tok_multi")

    assert reply == {
        "reply": "可以，打开这个入口：https://example.test/import\n登录或验证邮箱后，点击授权",
        "output_id": "out_1",
        "output_ids": ["out_1", "out_2"],
        "causal_inbound_event_id": "in_evt_multi",
        "business_conversation_key": "conv_key_multi",
    }
    assert [query["_id"] for query, _update in mongo.updates] == ["out_1", "out_2"]
    assert {message["status"] for message in mongo.messages} == {"handled"}


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
