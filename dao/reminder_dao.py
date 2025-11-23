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
    
    def find_pending_reminders(self, current_time: int, time_window: int = 1800) -> List[Dict]:
        """
        查找待触发的提醒
        
        Args:
            current_time: 当前时间戳
            time_window: 时间窗口（秒），默认30分钟
            
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
                              status: Optional[str] = None) -> List[Dict]:
        """查找用户的所有提醒"""
        query = {"user_id": user_id}
        if status:
            query["status"] = status
        return list(self.collection.find(query).sort("next_trigger_time", 1))
    
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
        """标记提醒为已触发"""
        update_data = {
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
        """重新安排提醒时间（用于周期提醒）"""
        return self.update_reminder(reminder_id, {
            "next_trigger_time": next_time,
            "status": "confirmed"
        })
    
    def delete_reminder(self, reminder_id: str) -> bool:
        """删除提醒"""
        result = self.collection.delete_one({"reminder_id": reminder_id})
        return result.deleted_count > 0
    
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
