from unittest.mock import MagicMock


def test_stream_consumer_ack_on_success():
    from agent.runner.message_processor import consume_stream_batch

    redis_client = MagicMock()
    redis_client.xreadgroup.return_value = [
        ("coke:input", [("1-0", {b"message_id": b"abc"})])
    ]

    mongo = MagicMock()
    mongo.find_one.return_value = {"_id": "abc", "status": "pending"}

    consume_stream_batch(redis_client, mongo)
    redis_client.xack.assert_called_once()
