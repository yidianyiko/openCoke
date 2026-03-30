from unittest.mock import MagicMock


def test_publish_input_event_writes_stream_entry():
    from util.redis_stream import publish_input_event

    mock_redis = MagicMock()

    publish_input_event(mock_redis, "abc123", "wechat", 123)
    mock_redis.xadd.assert_called_once()
