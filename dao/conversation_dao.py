import sys

sys.path.append(".")

from util.log_util import get_logger

logger = get_logger(__name__)

from typing import Dict, List, Optional, Tuple

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.cursor import Cursor

from conf.config import CONF


class ConversationDAO:
    """
    会话模型类，提供conversations集合的增删改查操作

    Conversation 数据结构：
    {
        "_id": ObjectId,
        "chatroom_name": str | None,  # None 表示单聊，非 None 表示群聊
        "talkers": [
            {"id": str, "nickname": str},
            ...
        ],
        "platform": str,  # "wechat", "telegram", etc.
        "conversation_info": {
            "chat_history": [
                {"role": str, "message": str, "timestamp": int},
                ...
            ],
            "input_messages": [...],
            "input_messages_str": str,
            "chat_history_str": str,
            "photo_history": [...],
            "future": {
                "timestamp": int | None,
                "action": str | None,
                "proactive_times": int,
                "status": str  # "pending", "scheduled", etc.
            },
            "turn_sent_contents": [str, ...]
        }
    }
    """

    @staticmethod
    def ensure_conversation_info_structure(conversation: Dict) -> Dict:
        """
        确保会话的 conversation_info 结构完整
        用于向后兼容旧数据

        Args:
            conversation: 会话数据

        Returns:
            Dict: 结构完整的会话数据
        """
        if "conversation_info" not in conversation:
            conversation["conversation_info"] = {}

        info = conversation["conversation_info"]

        # 确保所有必要字段存在
        if "chat_history" not in info:
            info["chat_history"] = []
        if "input_messages" not in info:
            info["input_messages"] = []
        if "input_messages_str" not in info:
            info["input_messages_str"] = ""
        if "chat_history_str" not in info:
            info["chat_history_str"] = ""
        if "photo_history" not in info:
            info["photo_history"] = []
        if "future" not in info:
            info["future"] = {
                "timestamp": None,
                "action": None,
                "proactive_times": 0,
                "status": "pending",
            }
        else:
            # 确保 future 的子字段存在
            future = info["future"]
            if "timestamp" not in future:
                future["timestamp"] = None
            if "action" not in future:
                future["action"] = None
            if "proactive_times" not in future:
                future["proactive_times"] = 0
            if "status" not in future:
                future["status"] = "pending"
        if "turn_sent_contents" not in info:
            info["turn_sent_contents"] = []

        return conversation

    def __init__(
        self,
        mongo_uri: str = "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name: str = CONF["mongodb"]["mongodb_name"],
    ):
        """
        初始化Conversation类

        Args:
            mongo_uri: MongoDB连接URI
            db_name: 数据库名称
        """
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection: Collection = self.db.conversations

    def create_indexes(self):
        """创建必要的索引"""
        # 为平台创建索引
        self.collection.create_index([("platform", 1)])

        # 为群聊名称创建索引
        self.collection.create_index([("chatroom_name", 1)])

        # 为talkers.id创建索引，支持按参与者查询
        self.collection.create_index([("talkers.id", 1)])
        self.collection.create_index([("talkers.db_user_id", 1)])

        # 创建组合索引，优化单聊查询
        self.collection.create_index(
            [("platform", 1), ("chatroom_name", 1), ("talkers.id", 1)]
        )

    def create_conversation(self, conversation_data: Dict) -> str:
        """
        创建新会话

        Args:
            conversation_data: 会话数据字典

        Returns:
            str: 插入的会话ID
        """
        if "_id" in conversation_data and isinstance(conversation_data["_id"], str):
            conversation_data["_id"] = ObjectId(conversation_data["_id"])

        result = self.collection.insert_one(conversation_data)
        return str(result.inserted_id)

    def get_conversation_by_id(self, conversation_id: str) -> Optional[Dict]:
        """
        通过ID获取会话

        Args:
            conversation_id: 会话ID

        Returns:
            Optional[Dict]: 会话数据或None
        """
        if not conversation_id:
            return None

        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError, InvalidId):
            return None

        conversation = self.collection.find_one({"_id": object_id})
        if conversation:
            conversation = self.ensure_conversation_info_structure(conversation)
        return conversation

    def get_private_conversation(
        self, platform: str, user_id1: str, user_id2: str
    ) -> Optional[Dict]:
        """
        获取两个用户之间的单聊会话

        Args:
            platform: 平台名称
            user_id1: 第一个用户ID
            user_id2: 第二个用户ID

        Returns:
            Optional[Dict]: 会话数据或None
        """
        if not platform or not user_id1 or not user_id2:
            return None

        # 构建查询条件：平台匹配，不是群聊，且两个用户都在talkers中
        query = {
            "platform": platform,
            "chatroom_name": None,
            "talkers.id": {"$all": [user_id1, user_id2]},
            # 确保只有这两个用户（即talkers数组长度为2）
            "$where": "this.talkers.length === 2",
        }

        conversation = self.collection.find_one(query)
        if conversation:
            conversation = self.ensure_conversation_info_structure(conversation)
        return conversation

    def get_private_conversation_by_db_user_ids(
        self, platform: str, db_user_id1: str, db_user_id2: str
    ) -> Optional[Dict]:
        if not platform or not db_user_id1 or not db_user_id2:
            return None

        query = {
            "platform": platform,
            "chatroom_name": None,
            "talkers.db_user_id": {"$all": [db_user_id1, db_user_id2]},
            "$where": "this.talkers.length === 2",
        }

        conversation = self.collection.find_one(query)
        if conversation:
            conversation = self.ensure_conversation_info_structure(conversation)
        return conversation

    def get_group_conversation(
        self, platform: str, chatroom_name: str
    ) -> Optional[Dict]:
        """
        获取群聊会话

        Args:
            platform: 平台名称
            chatroom_name: 群聊名称

        Returns:
            Optional[Dict]: 会话数据或None
        """
        if not platform or not chatroom_name:
            return None

        query = {"platform": platform, "chatroom_name": chatroom_name}

        conversation = self.collection.find_one(query)
        if conversation:
            conversation = self.ensure_conversation_info_structure(conversation)
        return conversation

    def update_conversation(self, conversation_id: str, update_data: Dict) -> bool:
        """
        更新会话信息

        Args:
            conversation_id: 会话ID
            update_data: 要更新的数据

        Returns:
            bool: 更新是否成功
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError):
            return False

        # 创建一个只包含要更新字段的字典
        update_fields = {"$set": update_data}

        result = self.collection.update_one({"_id": object_id}, update_fields)

        return result.modified_count > 0

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        删除会话

        Args:
            conversation_id: 会话ID

        Returns:
            bool: 删除是否成功
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError):
            return False

        result = self.collection.delete_one({"_id": object_id})
        return result.deleted_count > 0

    def find_conversations(
        self, query: Dict = None, limit: int = 0, skip: int = 0, sort=None
    ) -> Cursor:
        """
        查找符合条件的会话

        Args:
            query: 查询条件
            limit: 最大返回数量
            skip: 跳过的文档数
            sort: 排序字段

        Returns:
            Cursor: MongoDB游标
        """
        if query is None:
            query = {}

        cursor = self.collection.find(query)

        if skip > 0:
            cursor = cursor.skip(skip)

        if limit > 0:
            cursor = cursor.limit(limit)

        if sort:
            cursor = cursor.sort(sort)

        return list(cursor)

    def find_conversations_by_user(
        self, user_id: str, platform: Optional[str] = None, include_groups: bool = True
    ) -> List[Dict]:
        """
        查找用户参与的所有会话

        Args:
            user_id: 用户ID
            platform: 可选平台过滤
            include_groups: 是否包含群聊

        Returns:
            List[Dict]: 会话列表
        """
        query = {"talkers.id": user_id}

        if platform:
            query["platform"] = platform

        if not include_groups:
            query["chatroom_name"] = None

        cursor = self.collection.find(query)
        return list(cursor)

    def add_user_to_conversation(
        self, conversation_id: str, user_id: str, nickname: str
    ) -> bool:
        """
        向会话添加用户

        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            nickname: 用户在会话中的昵称

        Returns:
            bool: 添加是否成功
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError):
            return False

        # 检查用户是否已在会话中
        conversation = self.collection.find_one(
            {"_id": object_id, "talkers.id": user_id}
        )

        if conversation:
            # 用户已在会话中
            return False

        # 添加新用户到talkers数组
        result = self.collection.update_one(
            {"_id": object_id},
            {"$push": {"talkers": {"id": user_id, "nickname": nickname}}},
        )

        return result.modified_count > 0

    def remove_user_from_conversation(self, conversation_id: str, user_id: str) -> bool:
        """
        从会话移除用户

        Args:
            conversation_id: 会话ID
            user_id: 用户ID

        Returns:
            bool: 移除是否成功
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError):
            return False

        result = self.collection.update_one(
            {"_id": object_id}, {"$pull": {"talkers": {"id": user_id}}}
        )

        return result.modified_count > 0

    def update_user_nickname(
        self, conversation_id: str, user_id: str, new_nickname: str
    ) -> bool:
        """
        更新用户在会话中的昵称

        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            new_nickname: 新昵称

        Returns:
            bool: 更新是否成功
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError):
            return False

        result = self.collection.update_one(
            {"_id": object_id, "talkers.id": user_id},
            {"$set": {"talkers.$.nickname": new_nickname}},
        )

        return result.modified_count > 0

    def rename_group(self, conversation_id: str, new_name: str) -> bool:
        """
        重命名群聊

        Args:
            conversation_id: 会话ID
            new_name: 新群名称

        Returns:
            bool: 重命名是否成功
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError):
            return False

        # 验证这是一个群聊
        conversation = self.collection.find_one(
            {"_id": object_id, "chatroom_name": {"$ne": None}}
        )

        if not conversation:
            return False

        result = self.collection.update_one(
            {"_id": object_id}, {"$set": {"chatroom_name": new_name}}
        )

        return result.modified_count > 0

    def get_or_create_private_conversation(
        self,
        platform: str,
        user_id1: str,
        nickname1: str,
        user_id2: str,
        nickname2: str,
        db_user_id1: str | None = None,
        db_user_id2: str | None = None,
    ) -> Tuple[str, bool]:
        """
        获取或创建单聊会话

        Args:
            platform: 平台
            user_id1: 第一个用户ID
            nickname1: 第一个用户昵称
            user_id2: 第二个用户ID
            nickname2: 第二个用户昵称

        Returns:
            Tuple[str, bool]: 会话ID和是否新创建的标志
        """
        # 先尝试查找现有会话
        existing = self.get_private_conversation(platform, user_id1, user_id2)

        if existing:
            return str(existing["_id"]), False

        # 创建新会话，初始化完整的 conversation_info 结构
        talkers = [
            {"id": user_id1, "nickname": nickname1},
            {"id": user_id2, "nickname": nickname2},
        ]
        if db_user_id1:
            talkers[0]["db_user_id"] = db_user_id1
        if db_user_id2:
            talkers[1]["db_user_id"] = db_user_id2

        new_conversation = {
            "chatroom_name": None,
            "talkers": talkers,
            "platform": platform,
            "conversation_info": {
                "chat_history": [],
                "input_messages": [],
                "input_messages_str": "",
                "chat_history_str": "",
                "photo_history": [],
                "future": {
                    "timestamp": None,
                    "action": None,
                    "proactive_times": 0,
                    "status": "pending",
                },
                "turn_sent_contents": [],
            },
        }

        conversation_id = self.create_conversation(new_conversation)
        return conversation_id, True

    def get_or_create_group_conversation(
        self, platform: str, chatroom_name: str, initial_talkers: List[Dict] = None
    ) -> Tuple[str, bool]:
        """
        获取或创建群聊会话

        Args:
            platform: 平台
            chatroom_name: 群聊名称
            initial_talkers: 初始参与者列表 [{"id": "xxx", "nickname": "xxx"}, ...]

        Returns:
            Tuple[str, bool]: 会话ID和是否新创建的标志
        """
        # 先尝试查找现有群聊
        existing = self.get_group_conversation(platform, chatroom_name)

        if existing:
            return str(existing["_id"]), False

        # 创建新群聊，初始化完整的 conversation_info 结构
        new_conversation = {
            "chatroom_name": chatroom_name,
            "talkers": initial_talkers or [],
            "platform": platform,
            "conversation_info": {
                "chat_history": [],
                "input_messages": [],
                "input_messages_str": "",
                "chat_history_str": "",
                "photo_history": [],
                "future": {
                    "timestamp": None,
                    "action": None,
                    "proactive_times": 0,
                    "status": "pending",
                },
                "turn_sent_contents": [],
            },
        }

        conversation_id = self.create_conversation(new_conversation)
        return conversation_id, True

    def update_conversation_info(self, conversation_id: str, info_data: Dict) -> bool:
        """
        更新会话算法侧信息

        Args:
            conversation_id: 会话ID
            info_data: 算法侧信息

        Returns:
            bool: 更新是否成功
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError):
            return False

        result = self.collection.update_one(
            {"_id": object_id}, {"$set": {"conversation_info": info_data}}
        )

        return result.modified_count > 0

    def count_conversations(self, query: Dict = None) -> int:
        """
        计算符合条件的会话数量

        Args:
            query: 查询条件

        Returns:
            int: 会话数量
        """
        if query is None:
            query = {}

        return self.collection.count_documents(query)

    def get_recent_group_messages(
        self, chatroom_name: str, limit: int = 10
    ) -> List[Dict]:
        """
        获取群聊最近 N 条消息（包含用户消息和机器人回复）

        从 inputmessages 和 outputmessages 集合中获取指定群聊的最近消息，
        按时间戳合并排序后返回，用于构建群聊上下文。

        Args:
            chatroom_name: 群聊 ID (如 "xxx@chatroom")
            limit: 最多返回的消息数量

        Returns:
            List[Dict]: 消息列表，按时间正序排列（旧消息在前）
        """
        if not chatroom_name:
            return []

        # 1. 从 inputmessages 查询用户消息
        inputmessages_collection = self.db["inputmessages"]
        input_cursor = (
            inputmessages_collection.find(
                {"chatroom_name": chatroom_name, "status": "handled"}
            )
            .sort("input_timestamp", -1)
            .limit(limit)
        )
        input_messages = list(input_cursor)

        # 2. 从 outputmessages 查询机器人回复
        outputmessages_collection = self.db["outputmessages"]
        output_cursor = (
            outputmessages_collection.find(
                {"chatroom_name": chatroom_name, "status": "handled"}
            )
            .sort("expect_output_timestamp", -1)
            .limit(limit)
        )
        output_messages = list(output_cursor)

        # 3. 合并并按时间戳排序
        all_messages = input_messages + output_messages

        def get_timestamp(msg):
            if "input_timestamp" in msg:
                return msg["input_timestamp"]
            elif "expect_output_timestamp" in msg:
                return msg["expect_output_timestamp"]
            return 0

        all_messages.sort(key=get_timestamp, reverse=True)
        recent_messages = all_messages[:limit]

        # 4. 反转为正序（旧消息在前）
        recent_messages.reverse()

        return recent_messages

    def close(self):
        """关闭MongoDB连接"""
        self.client.close()

