from util.redis_client import RedisClient


def test_redis_client_uses_config_defaults():
    client = RedisClient.from_config()
    assert client.host == "127.0.0.1"
    assert client.port == 6379
