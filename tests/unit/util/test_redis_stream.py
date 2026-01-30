from unittest.mock import MagicMock

from util.redis_stream import publish_input_event


def test_publish_input_event_calls_xadd():
    redis_client = MagicMock()
    publish_input_event(redis_client, "abc123", "wechat", 1234567890)
    redis_client.xadd.assert_called_once()
