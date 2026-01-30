# -*- coding: utf-8 -*-
import sys

sys.path.append(".")
import time

from util.log_util import get_logger

logger = get_logger(__name__)

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.redis_client import RedisClient
from util.redis_stream import publish_input_event

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None

# 用户 ID（发送消息的人）
from_user = "6916f48dd16895f164265eea"  # 不辣的皮皮 (wx_test_user)
# 角色 ID（接收消息的 AI 角色）
to_user = "6916d8f79c455f8b8d06ecec"  # Coke (wxid_58bfckbpioh822)

mongo = MongoDBBase()
user_dao = UserDAO()
redis_conf = RedisClient.from_config()
redis_client = (
    redis.Redis(host=redis_conf.host, port=redis_conf.port, db=redis_conf.db)
    if redis is not None
    else None
)


def _publish_stream_event(message_id: str, platform: str, ts: int) -> None:
    if redis_client is None:
        return
    publish_input_event(
        redis_client,
        message_id,
        platform,
        ts,
        stream_key=redis_conf.stream_key,
    )


user = user_dao.get_user_by_id(from_user)
user_name = user["platforms"]["wechat"]["nickname"]

while True:
    input_text = input(user_name + "：")
    now = int(time.time())
    message = {
        "input_timestamp": now,  # 输入时的时间戳秒级
        "handled_timestamp": now,  # 处理完毕时的时间戳秒级
        "status": "pending",  # 标记处理状态：pending待处理，handled处理完毕，canceled不处理，failed处理失败
        "from_user": from_user,  # 来源uid
        "platform": "wechat",  # 来源平台
        "chatroom_name": None,  # 如果有值，则来自群聊；否则是私聊
        "to_user": to_user,  # 目标用户；群聊时，值为None
        "message_type": "text",  # 包括：
        "message": input_text,  # 实际消息，格式另行约定
        "metadata": {},
    }

    id = mongo.insert_one("inputmessages", message)
    _publish_stream_event(id, message.get("platform", "wechat"), now)
    print("sent.")
