import sys

sys.path.append(".")
import time

from dao.mongo import MongoDBBase
from util.time_util import validate_timestamp

# 模块级单例，避免每次调用创建新连接
_mongo = MongoDBBase()


def read_top_inputmessage(to_user=None, status=None, platform=None):
    query = {}
    if to_user:
        query["to_user"] = to_user
    if status:
        query["status"] = status
    if platform:
        query["platform"] = platform
    return _mongo.find_one("inputmessages", query)


def read_top_inputmessages(
    to_user=None, status=None, platform=None, limit=16, max_handle_age=7200
):
    query = {}
    if to_user:
        query["to_user"] = to_user
    if status:
        query["status"] = status
    if platform:
        query["platform"] = platform

    now = int(time.time())
    # BUG-010 fix: Ensure timestamp comparison uses validated values
    query["input_timestamp"] = {"$gt": now - max_handle_age}
    return _mongo.find_many("inputmessages", query, limit=limit)


def get_locked_conversation_ids():
    """
    获取当前所有被锁定的会话ID列表

    Returns:
        set: 被锁定的会话ID集合
    """
    import datetime

    locks = _mongo.find_many(
        "locks",
        {
            "resource_type": "conversation",
            "expires_at": {"$gt": datetime.datetime.now(datetime.UTC)},
        },
        limit=100,
    )

    # 从 resource_id 中提取 conversation_id（格式为 "conversation:xxx"）
    locked_ids = set()
    for lock in locks:
        resource_id = lock.get("resource_id", "")
        if resource_id.startswith("conversation:"):
            locked_ids.add(resource_id.replace("conversation:", ""))

    return locked_ids


def save_inputmessage(inputmessage):
    return _mongo.replace_one(
        "inputmessages", {"_id": inputmessage["_id"]}, inputmessage
    )


def save_outputmessage(outputmessage):
    return _mongo.replace_one(
        "outputmessages", {"_id": outputmessage["_id"]}, outputmessage
    )


def read_all_inputmessages(from_user, to_user, platform, status=None):
    query = {
        "platform": platform,
        "from_user": from_user,
        "to_user": to_user,
    }
    if status:
        query["status"] = status
    return _mongo.find_many("inputmessages", query)


def find_one_byid(message_id, message_type="inputmessages"):
    return _mongo.find_one(message_type, {"_id": message_id})


def update_message_status_safe(message_id, new_status, expected_status="pending"):
    """
     乐观锁更新消息状态：只有当状态是预期值时才更新

     解决问题：
    -P9: 锁超时后原 Worker 和新 Worker 同时处理同一消息
    -MT-4: 锁超时后重复处理

     Args:
         message_id: 消息ID
         new_status: 新状态
         expected_status: 预期的当前状态（默认 pending）

     Returns:
         bool: 是否更新成功
    """
    modified_count = _mongo.update_one(
        "inputmessages",
        {"_id": message_id, "status": expected_status},
        {"$set": {"status": new_status, "handled_timestamp": int(time.time())}},
    )
    return modified_count > 0


def increment_retry_count(message_id, error_msg=None):
    """
    增加消息重试计数

    Args:
        message_id: 消息ID
        error_msg: 错误信息（可选，截断到500字符）

    Returns:
        int: 更新后的重试次数，失败返回 -1
    """
    update_data = {"$inc": {"retry_count": 1}}
    if error_msg:
        update_data["$set"] = {"last_error": str(error_msg)[:500]}

    modified_count = _mongo.update_one(
        "inputmessages", {"_id": message_id}, update_data
    )

    if modified_count > 0:
        msg = _mongo.find_one("inputmessages", {"_id": message_id})
        return msg.get("retry_count", 0) if msg else -1
    return -1


def increment_rollback_count(message_id):
    """
    增加消息 rollback 计数

    Args:
        message_id: 消息ID

    Returns:
        int: 更新后的 rollback 次数，失败返回 -1
    """
    modified_count = _mongo.update_one(
        "inputmessages", {"_id": message_id}, {"$inc": {"rollback_count": 1}}
    )

    if modified_count > 0:
        msg = _mongo.find_one("inputmessages", {"_id": message_id})
        return msg.get("rollback_count", 0) if msg else -1
    return -1


def set_hold_status(message_id):
    """
    设置消息为 hold 状态，并记录 hold 开始时间

    Args:
        message_id: 消息ID

    Returns:
        bool: 是否更新成功
    """
    modified_count = _mongo.update_one(
        "inputmessages",
        {"_id": message_id},
        {"$set": {"status": "hold", "hold_started_at": int(time.time())}},
    )
    return modified_count > 0
