from unittest.mock import MagicMock


def test_ecloud_input_publishes_stream_event(monkeypatch):
    from connector.ecloud import ecloud_input

    mock_redis = MagicMock()
    monkeypatch.setattr(ecloud_input, "redis_client", mock_redis)

    ecloud_input._publish_stream_event("abc123", "wechat", 123)
    mock_redis.xadd.assert_called_once()
