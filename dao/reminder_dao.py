# -*- coding: utf-8 -*-
import sys

sys.path.append(".")

import re
import time
import uuid

from util.log_util import get_logger

logger = get_logger(__name__)

from typing import Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection

from conf.config import CONF


class ReminderDAO:
    """提醒任务数据访问层"""

    def __init__(
        self,
        mongo_uri: str = "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name: str = CONF["mongodb"]["mongodb_name"],
    ):
        """初始化 ReminderDAO"""
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection: Collection = self.db.reminders

    def create_indexes(self):
        """创建必要的索引"""
        self.collection.create_index([("conversation_id", 1)])
        self.collection.create_index([("status", 1), ("next_trigger_time", 1)])
        self.collection.create_index([("reminder_id", 1)], unique=True)
        self.collection.create_index([("user_id", 1), ("status", 1)])
        # 新增：list_id 复合索引
        self.collection.create_index([("list_id", 1), ("user_id", 1), ("status", 1)])
        logger.info("Reminder indexes created")

    def create_reminder(self, reminder_data: Dict) -> str:
        """
        创建新提醒

        Args:
            reminder_data: 提醒数据字典

        Returns:
            str: 插入的提醒ID

        Raises:
            ValueError: 如果 user_id 为空或缺失
        """
        # BUG-009 fix: Validate that user_id is non-empty
        user_id = reminder_data.get("user_id")
        if not user_id or (isinstance(user_id, str) and not user_id.strip()):
            raise ValueError("user_id is required and cannot be empty")

        # 确保必要字段存在
        if "reminder_id" not in reminder_data:
            reminder_data["reminder_id"] = str(uuid.uuid4())

        if "created_at" not in reminder_data:
            reminder_data["created_at"] = int(time.time())

        if "updated_at" not in reminder_data:
            reminder_data["updated_at"] = int(time.time())

        if "triggered_count" not in reminder_data:
            reminder_data["triggered_count"] = 0

        if "status" not in reminder_data:
            reminder_data["status"] = "active"

        # 新增：list_id 默认值
        if "list_id" not in reminder_data:
            reminder_data["list_id"] = "inbox"

        result = self.collection.insert_one(reminder_data)
        return str(result.inserted_id)

    def get_reminder_by_id(self, reminder_id: str) -> Optional[Dict]:
        """通过 reminder_id 获取提醒"""
        return self.collection.find_one({"reminder_id": reminder_id})

    def get_reminder_by_object_id(self, object_id: str) -> Optional[Dict]:
        """通过 MongoDB _id 获取提醒"""
        try:
            oid = ObjectId(object_id)
            return self.collection.find_one({"_id": oid})
        except (TypeError, ValueError):
            return None

    def find_pending_reminders(
        self, current_time: int, time_window: int = 60
    ) -> List[Dict]:
        """
        查找待触发的提醒

        Args:
            current_time: 当前时间戳
            time_window: 保留参数以保持API兼容性（不再使用）

        Returns:
            List[Dict]: 待触发的提醒列表

        Note:
            不再限制时间下界，避免错过的提醒永远无法触发。
            重复触发由 mark_as_triggered 的状态变更（active -> triggered）防止。
            阶段二状态重构：confirmed/pending -> active

            trigger_time=None 的任务（inbox 待安排任务）会被自然过滤，
            因为 None 不满足 $lte 比较条件。
        """
        query = {
            "status": "active",
            "next_trigger_time": {"$lte": current_time},  # None 会被自动排除
        }
        # 添加 limit 防止积压过多时一次性加载太多
        return list(self.collection.find(query).sort("next_trigger_time", 1).limit(100))

    def find_reminders_by_conversation(
        self, conversation_id: str, status: Optional[str] = None
    ) -> List[Dict]:
        """查找会话的所有提醒"""
        query = {"conversation_id": conversation_id}
        if status:
            query["status"] = status
        return list(self.collection.find(query))

    def find_reminders_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        status_list: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        查找用户的所有提醒

        Args:
            user_id: 用户ID
            status: 单个状态过滤（向后兼容）
            status_list: 多个状态过滤，如 ["confirmed", "pending"]

        Note:
            支持 trigger_time=None 的任务，排序时 None 值会排在最后
        """
        query = {"user_id": user_id}
        if status_list:
            query["status"] = {"$in": status_list}
        elif status:
            query["status"] = status

        # MongoDB 排序：null 值会排在最后（升序时）
        return list(self.collection.find(query).sort("next_trigger_time", 1))

    def filter_reminders(
        self,
        user_id: str,
        status_list: Optional[List[str]] = None,
        reminder_type: Optional[str] = None,
        keyword: Optional[str] = None,
        trigger_after: Optional[int] = None,
        trigger_before: Optional[int] = None,
    ) -> List[Dict]:
        """
        灵活筛选用户的提醒（阶段二新增）

        Args:
            user_id: 用户ID
            status_list: 状态过滤，可选值: ["active", "triggered", "completed"]
                        默认: ["active"] - 只查询未完成的提醒
            reminder_type: 提醒类型，可选值: "one_time" | "recurring"
            keyword: 关键字，模糊匹配 title
            trigger_after: 时间范围开始（Unix时间戳）
            trigger_before: 时间范围结束（Unix时间戳）

        Returns:
            List[Dict]: 匹配的提醒列表，按 trigger_time 升序排序
        """
        # 默认只查询 active 状态
        if status_list is None:
            status_list = ["active"]

        query = {"user_id": user_id, "status": {"$in": status_list}}

        # 提醒类型筛选
        if reminder_type == "one_time":
            query["$or"] = [
                {"recurrence.enabled": False},
                {"recurrence.enabled": {"$exists": False}},
            ]
        elif reminder_type == "recurring":
            query["recurrence.enabled"] = True

        # 关键字搜索
        if keyword and keyword.strip():
            safe_keyword = re.escape(keyword.strip())
            query["title"] = {"$regex": safe_keyword, "$options": "i"}

        # 时间范围筛选
        if trigger_after is not None or trigger_before is not None:
            time_query = {}
            if trigger_after is not None:
                time_query["$gte"] = trigger_after
            if trigger_before is not None:
                time_query["$lte"] = trigger_before
            query["next_trigger_time"] = time_query

        return list(self.collection.find(query).sort("next_trigger_time", 1))

    def complete_reminders_by_keyword(
        self,
        user_id: str,
        keyword: str,
    ) -> tuple[int, List[Dict]]:
        """
        根据关键字完成用户的提醒（阶段二新增）

        Args:
            user_id: 用户ID
            keyword: 搜索关键字

        Returns:
            tuple[int, List[Dict]]: (完成数量, 被完成的提醒列表)
        """
        # 可以完成 active 或 triggered 状态的提醒
        # triggered 状态表示提醒已触发但用户尚未确认完成
        if not keyword or not keyword.strip():
            logger.warning(
                f"Empty keyword provided for user {user_id}, returning empty list"
            )
            return 0, []

        safe_keyword = re.escape(keyword.strip())
        query = {
            "user_id": user_id,
            "status": {"$in": ["active", "triggered"]},
            "title": {"$regex": safe_keyword, "$options": "i"},
        }

        matched = list(self.collection.find(query))
        if not matched:
            return 0, []

        # 记录被完成的提醒信息
        completed_reminders = [
            {"reminder_id": r.get("reminder_id"), "title": r.get("title")}
            for r in matched
        ]

        # 更新状态为 completed
        reminder_ids = [r.get("reminder_id") for r in matched]
        result = self.collection.update_many(
            {"user_id": user_id, "reminder_id": {"$in": reminder_ids}},
            {"$set": {"status": "completed", "updated_at": int(time.time())}},
        )

        logger.info(
            f"Completed {result.modified_count} reminders by keyword '{keyword}' for user {user_id}"
        )
        return result.modified_count, completed_reminders

    def find_similar_reminder(
        self,
        user_id: str,
        title: str,
        trigger_time: int,
        recurrence_type: Optional[str] = None,
        time_tolerance: int = 300,
    ) -> Optional[Dict]:
        """
        查找相似的有效提醒（用于去重检查）

        去重判定规则：
        1. 同一用户
        2. 标题完全相同
        3. 触发时间在容差范围内（默认5分钟）
        4. 周期类型相同
        5. 状态为有效状态（active）

        Args:
            user_id: 用户ID
            title: 提醒标题
            trigger_time: 触发时间戳
            recurrence_type: 周期类型（none/daily/weekly等）
            time_tolerance: 时间容差（秒），默认300秒（5分钟）

        Returns:
            Optional[Dict]: 找到的相似提醒，或 None

        Note:
            阶段二状态重构：confirmed/pending -> active
        """
        # 处理周期类型：none 和 None 视为等同
        normalized_recurrence = (
            None if recurrence_type in (None, "none") else recurrence_type
        )

        query = {
            "user_id": user_id,
            "title": title,
            "status": "active",
            "next_trigger_time": {
                "$gte": trigger_time - time_tolerance,
                "$lte": trigger_time + time_tolerance,
            },
        }

        # 查询周期类型匹配
        if normalized_recurrence is None:
            # 非周期提醒：recurrence.type 为 null 或 recurrence.enabled 为 false
            query["$or"] = [{"recurrence.type": None}, {"recurrence.enabled": False}]
        else:
            query["recurrence.type"] = normalized_recurrence

        return self.collection.find_one(query)

    def find_reminder_at_same_time(
        self, user_id: str, trigger_time: int, time_tolerance: int = 300
    ) -> Optional[Dict]:
        """
        查找同一时间点的有效提醒（不考虑标题）

        用于检测同一时间是否已有提醒，支持内容追加场景.

        Args:
            user_id: 用户ID
            trigger_time: 触发时间戳
            time_tolerance: 时间容差（秒），默认300秒（5分钟）

        Returns:
            Optional[Dict]: 找到的同时间提醒，或 None

        Note:
            阶段二状态重构：confirmed/pending -> active
        """
        query = {
            "user_id": user_id,
            "status": "active",
            "next_trigger_time": {
                "$gte": trigger_time - time_tolerance,
                "$lte": trigger_time + time_tolerance,
            },
        }

        return self.collection.find_one(query)

    def append_to_reminder(self, reminder_id: str, additional_title: str) -> bool:
        """
        追加内容到已有提醒

        将新的提醒内容追加到已有提醒的标题和 action_template 中.

        Args:
            reminder_id: 提醒ID
            additional_title: 要追加的内容

        Returns:
            bool: 追加是否成功
        """
        existing = self.get_reminder_by_id(reminder_id)
        if not existing:
            return False

        current_title = existing.get("title", "")
        current_template = existing.get("action_template", "")

        # 追加新内容，用分号分隔
        new_title = f"{current_title}；{additional_title}"
        new_template = f"{current_template}；记得{additional_title}"

        update_data = {
            "title": new_title,
            "action_template": new_template,
            "updated_at": int(time.time()),
        }

        result = self.collection.update_one(
            {"reminder_id": reminder_id}, {"$set": update_data}
        )
        return result.modified_count > 0

    def update_reminder(self, reminder_id: str, update_data: Dict) -> bool:
        """
        更新提醒

        Args:
            reminder_id: 提醒ID
            update_data: 要更新的数据

        Returns:
            bool: 更新是否成功
        """
        update_data["updated_at"] = int(time.time())
        result = self.collection.update_one(
            {"reminder_id": reminder_id}, {"$set": update_data}
        )
        return result.modified_count > 0

    def mark_as_triggered(self, reminder_id: str) -> bool:
        """标记提醒为已触发（将状态改为 triggered，避免重复触发）"""
        update_data = {
            "status": "triggered",
            "last_triggered_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        result = self.collection.update_one(
            {"reminder_id": reminder_id},
            {"$set": update_data, "$inc": {"triggered_count": 1}},
        )
        return result.modified_count > 0

    def cancel_reminder(self, reminder_id: str) -> bool:
        """取消提醒"""
        return self.update_reminder(reminder_id, {"status": "cancelled"})

    def complete_reminder(self, reminder_id: str) -> bool:
        """完成提醒（非周期提醒触发后）"""
        return self.update_reminder(reminder_id, {"status": "completed"})

    def reschedule_reminder(self, reminder_id: str, next_time: int) -> bool:
        """重新安排提醒时间（用于周期提醒），将状态重置为 active"""
        return self.update_reminder(
            reminder_id, {"next_trigger_time": next_time, "status": "active"}
        )

    def delete_reminder(self, reminder_id: str) -> bool:
        """删除提醒"""
        result = self.collection.delete_one({"reminder_id": reminder_id})
        return result.deleted_count > 0

    def delete_all_by_user(self, user_id: str) -> int:
        """
        删除用户的所有待办提醒

        Args:
            user_id: 用户ID

        Returns:
            int: 删除的提醒数量

        Note:
            阶段二状态重构：confirmed/pending -> active
        """
        # 只删除有效状态的提醒（active）
        result = self.collection.delete_many({"user_id": user_id, "status": "active"})
        logger.info(f"Deleted {result.deleted_count} reminders for user {user_id}")
        return result.deleted_count

    def find_reminders_by_keyword(
        self,
        user_id: str,
        keyword: str,
        status_list: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        根据关键字模糊匹配用户的提醒

        Args:
            user_id: 用户ID
            keyword: 搜索关键字，支持模糊匹配标题
            status_list: 状态过滤，默认只查有效提醒

        Returns:
            List[Dict]: 匹配的提醒列表

        Note:
            阶段二状态重构：confirmed/pending -> active
        """
        if status_list is None:
            status_list = ["active"]

        # BUG-010 fix: Empty or whitespace-only keyword should not match anything
        if not keyword or not keyword.strip():
            logger.warning(
                f"Empty keyword provided for user {user_id}, returning empty list"
            )
            return []

        # BUG-005 Medium fix: Escape regex special characters to prevent injection
        safe_keyword = re.escape(keyword.strip())

        query = {
            "user_id": user_id,
            "status": {"$in": status_list},
            "title": {"$regex": safe_keyword, "$options": "i"},  # 不区分大小写
        }
        return list(self.collection.find(query).sort("next_trigger_time", 1))

    def delete_reminders_by_keyword(
        self,
        user_id: str,
        keyword: str,
    ) -> tuple[int, List[Dict]]:
        """
        根据关键字删除用户的提醒

        Args:
            user_id: 用户ID
            keyword: 搜索关键字

        Returns:
            tuple[int, List[Dict]]: (删除数量, 被删除的提醒列表)

        Note:
            阶段二状态重构：confirmed/pending -> active
        """
        # 先查找匹配的提醒
        matched = self.find_reminders_by_keyword(user_id, keyword)
        if not matched:
            return 0, []

        # 记录被删除的提醒信息
        deleted_reminders = [
            {"reminder_id": r.get("reminder_id"), "title": r.get("title")}
            for r in matched
        ]

        # 删除匹配的提醒
        reminder_ids = [r.get("reminder_id") for r in matched]
        result = self.collection.delete_many(
            {
                "user_id": user_id,
                "reminder_id": {"$in": reminder_ids},
                "status": "active",
            }
        )

        logger.info(
            f"Deleted {result.deleted_count} reminders by keyword '{keyword}' for user {user_id}"
        )
        return result.deleted_count, deleted_reminders

    def update_reminders_by_keyword(
        self,
        user_id: str,
        keyword: str,
        update_data: Dict,
    ) -> tuple[int, List[Dict]]:
        """
        根据关键字更新用户的提醒

        Args:
            user_id: 用户ID
            keyword: 搜索关键字
            update_data: 要更新的数据

        Returns:
            tuple[int, List[Dict]]: (更新数量, 被更新的提醒列表)

        Note:
            阶段二状态重构：confirmed/pending -> active
        """
        # 先查找匹配的提醒
        matched = self.find_reminders_by_keyword(user_id, keyword)
        if not matched:
            return 0, []

        # 记录被更新的提醒信息
        updated_reminders = [
            {"reminder_id": r.get("reminder_id"), "title": r.get("title")}
            for r in matched
        ]

        # 添加更新时间
        update_data["updated_at"] = int(time.time())

        # 更新匹配的提醒
        reminder_ids = [r.get("reminder_id") for r in matched]
        result = self.collection.update_many(
            {
                "user_id": user_id,
                "reminder_id": {"$in": reminder_ids},
                "status": "active",
            },
            {"$set": update_data},
        )

        logger.info(
            f"Updated {result.modified_count} reminders by keyword '{keyword}' for user {user_id}"
        )
        return result.modified_count, updated_reminders

    def close(self):
        """关闭数据库连接"""
        self.client.close()


# 测试代码
if __name__ == "__main__":
    dao = ReminderDAO()
    dao.create_indexes()

    # 测试创建提醒
    test_reminder = {
        "conversation_id": "test_conv_123",
        "user_id": "test_user_456",
        "character_id": "test_char_789",
        "title": "测试提醒",
        "next_trigger_time": int(time.time()) + 3600,
        "time_original": "1小时后",
        "timezone": "Asia/Shanghai",
        "recurrence": {"enabled": False},
        "action_template": "这是一个测试提醒",
        "requires_confirmation": False,
    }

    reminder_id = dao.create_reminder(test_reminder)
    logger.info(f"Created reminder: {reminder_id}")

    # 测试查询
    reminders = dao.find_reminders_by_user("test_user_456")
    logger.info(f"Found {len(reminders)} reminders")

    dao.close()
