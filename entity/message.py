import sys
sys.path.append(".")
import time

from dao.mongo import MongoDBBase

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


def read_top_inputmessages(to_user=None, status=None, platform=None, limit=16, max_handle_age=7200):
    query = {}
    if to_user:
        query["to_user"] = to_user
    if status:
        query["status"] = status
    if platform:
        query["platform"] = platform
    
    now = int(time.time())
    query["input_timestamp"] = {"$gt": now - max_handle_age}
    return _mongo.find_many("inputmessages", query, limit=limit)


def save_inputmessage(inputmessage):
    return _mongo.replace_one("inputmessages", {"_id": inputmessage["_id"]}, inputmessage)


def save_outputmessage(outputmessage):
    return _mongo.replace_one("outputmessages", {"_id": outputmessage["_id"]}, outputmessage)


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