from __future__ import annotations

from typing import Any

import redis as redis_lib

from coke.config import Settings


def create_redis_client(settings: Settings) -> Any:
    return redis_lib.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
