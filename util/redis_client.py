from dataclasses import dataclass

from conf.config import CONF


@dataclass
class RedisClient:
    host: str
    port: int
    db: int
    stream_key: str
    group: str

    @classmethod
    def from_config(cls) -> "RedisClient":
        redis_conf = CONF.get("redis", {})
        return cls(
            host=redis_conf.get("host", "127.0.0.1"),
            port=int(redis_conf.get("port", 6379)),
            db=int(redis_conf.get("db", 0)),
            stream_key=redis_conf.get("stream", "coke:input"),
            group=redis_conf.get("group", "coke-workers"),
        )
