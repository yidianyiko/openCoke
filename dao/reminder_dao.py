# -*- coding: utf-8 -*-
import sys
sys.path.append(".")

import time
import uuid
import traceback
import logging
from logging import getLogger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

from pymongo import MongoClient
from pymongo.collection import Collection
from typing import Dict, List, Optional
from bson import ObjectId

from conf.config import CONF


class ReminderDAO:
    """提醒任务数据访问层"""
    
    def __init__(self, mongo_uri: str = "mongodb://" + CONF["mongodb"]["mongodb_ip"] + ":" + CONF["mongodb"]["mongodb_port"] + "/", 
                 db_name: str = CONF["mongodb"]["mongodb_name"]):
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
        logger.info("Reminder indexes created")
    
    def create_reminder(self, reminder_data: Dict) -> str:
        """
        创建新提醒
        
        Args:
            reminder_data: 提醒数据字典
            
        Returns:
            str: 插入的提醒ID
        """
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
            reminder_data["status"] = "confirmed"
        
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
        except:
            return None
    
    def find_pending_reminders(self, current_time: int, time_window: int = 60) -> List[Dict]:
        """
        查找待触发的提醒
        
        Args:
            current_time: 当前时间戳
            time_window: 时间窗口（秒），默认60秒，避免重复触发
            
        Returns:
            List[Dict]: 待触发的提醒列表
        """
        query = {
            "status": {"$in": ["confirmed", "pending"]},
            "next_trigger_time": {
                "$lte": current_time,
                "$gte": current_time - time_window
            }
        }
        return list(self.collection.find(query))
    
    def find_reminders_by_conversation(self, conversation_id: str, 
                                      status: Optional[str] = None) -> List[Dict]:
        """查找会话的所有提醒"""
        query = {"conversation_id": conversation_id}
        if status:
            query["status"] = status
        return list(self.collection.find(query))
    
    def find_reminders_by_user(self, user_id: str, 
                              status: Optional[str] = None,
                              status_list: Optional[List[str]] = None) -> List[Dict]:
        """
        查找用户的所有提醒
        
        Args:
            user_id: 用户ID
            status: 单个状态过滤（向后兼容）
            status_list: 多个状态过滤，如 ["confirmed", "pending"]
        """
        query = {"user_id": user_id}
        if status_list:
            query["status"] = {"$in": status_list}
        elif status:
            query["status"] = status
        return list(self.collection.find(query).sort("next_trigger_time", 1))
    
    def find_similar_reminder(
        self, 
        user_id: str, 
        title: str, 
        trigger_time: int,
        recurrence_type: Optional[str] = None,
        time_tolerance: int = 300
    ) -> Optional[Dict]:
        """
        查找相似的有效提醒（用于去重检查）
        
        去重判定规则：
        1. 同一用户
        2. 标题完全相同
        3. 触发时间在容差范围内（默认5分钟）
        4. 周期类型相同
        5. 状态为有效状态（confirmed/pending）
        
        Args:
            user_id: 用户ID
            title: 提醒标题
            trigger_time: 触发时间戳
            recurrence_type: 周期类型（none/daily/weekly等）
            time_tolerance: 时间容差（秒），默认300秒（5分钟）
            
        Returns:
            Optional[Dict]: 找到的相似提醒，或 None
        """
        # 处理周期类型：none 和 None 视为等同
        normalized_recurrence = None if recurrence_type in (None, "none") else recurrence_type
        
        query = {
            "user_id": user_id,
            "title": title,
            "status": {"$in": ["confirmed", "pending"]},
            "next_trigger_time": {
                "$gte": trigger_time - time_tolerance,
                "$lte": trigger_time + time_tolerance
            }
        }
        
        # 查询周期类型匹配
        if normalized_recurrence is None:
            # 非周期提醒：recurrence.type 为 null 或 recurrence.enabled 为 false
            query["$or"] = [
                {"recurrence.type": None},
                {"recurrence.enabled": False}
            ]
        else:
            query["recurrence.type"] = normalized_recurrence
        
        return self.collection.find_one(query)
    
    def find_reminder_at_same_time(
        self, 
        user_id: str, 
        trigger_time: int,
        time_tolerance: int = 300
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
        """
        query = {
            "user_id": user_id,
            "status": {"$in": ["confirmed", "pending"]},
            "next_trigger_time": {
                "$gte": trigger_time - time_tolerance,
                "$lte": trigger_time + time_tolerance
            }
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
            "updated_at": int(time.time())
        }
        
        result = self.collection.update_one(
            {"reminder_id": reminder_id},
            {"$set": update_data}
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
            {"reminder_id": reminder_id},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    def mark_as_triggered(self, reminder_id: str) -> bool:
        """标记提醒为已触发（将状态改为 triggered，避免重复触发）"""
        update_data = {
            "status": "triggered",
            "last_triggered_at": int(time.time()),
            "updated_at": int(time.time())
        }
        result = self.collection.update_one(
            {"reminder_id": reminder_id},
            {
                "$set": update_data,
                "$inc": {"triggered_count": 1}
            }
        )
        return result.modified_count > 0
    
    def cancel_reminder(self, reminder_id: str) -> bool:
        """取消提醒"""
        return self.update_reminder(reminder_id, {"status": "cancelled"})
    
    def complete_reminder(self, reminder_id: str) -> bool:
        """完成提醒（非周期提醒触发后）"""
        return self.update_reminder(reminder_id, {"status": "completed"})
    
    def reschedule_reminder(self, reminder_id: str, next_time: int) -> bool:
        """重新安排提醒时间（用于周期提醒），将状态重置为 confirmed"""
        return self.update_reminder(reminder_id, {
            "next_trigger_time": next_time,
            "status": "confirmed"
        })
    
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
        """
        # 只删除有效状态的提醒（confirmed/pending）
        result = self.collection.delete_many({
            "user_id": user_id,
            "status": {"$in": ["confirmed", "pending"]}
        })
        logger.info(f"Deleted {result.deleted_count} reminders for user {user_id}")
        return result.deleted_count
    
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
        "recurrence": {
            "enabled": False
        },
        "action_template": "这是一个测试提醒",
        "requires_confirmation": False
    }
    
    reminder_id = dao.create_reminder(test_reminder)
    logger.info(f"Created reminder: {reminder_id}")
    
    # 测试查询
    reminders = dao.find_reminders_by_user("test_user_456")
    logger.info(f"Found {len(reminders)} reminders")
    
    dao.close()
