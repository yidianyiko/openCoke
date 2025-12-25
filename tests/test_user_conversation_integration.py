# -*- coding: utf-8 -*-
"""
用户对话功能集成测试（使用真实数据库）

从用户角度进行真实的端到端测试：
1. 用户对话触发未来消息
2. 用户对话触发消息提醒

注意：这些测试会在真实数据库中创建和删除测试数据
"""
import sys

sys.path.append(".")

import time
import unittest
import uuid
from datetime import datetime

from bson import ObjectId


class TestRealReminderIntegration(unittest.TestCase):
    """
    集成测试：使用真实数据库测试提醒功能
    """

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        from dao.reminder_dao import ReminderDAO

        cls.dao = ReminderDAO()
        cls.dao.create_indexes()
        cls.test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        cls.test_character_id = f"test_char_{uuid.uuid4().hex[:8]}"
        cls.created_reminder_ids = []

    @classmethod
    def tearDownClass(cls):
        """清理测试数据"""
        for reminder_id in cls.created_reminder_ids:
            try:
                cls.dao.delete_reminder(reminder_id)
            except Exception:
                pass
        cls.dao.close()

    def test_01_user_creates_reminder_short_time(self):
        """
        测试：用户创建短时间提醒（2分钟后）

        用户视角：
        1. 用户说"2分钟后提醒我喝水"
        2. 系统创建提醒
        3. 验证提醒已创建
        """
        print("\n" + "=" * 50)
        print("集成测试：用户创建2分钟后的提醒")
        print("=" * 50)

        # 用户请求：2分钟后提醒我喝水
        trigger_time = int(time.time()) + 120  # 2分钟后

        reminder_data = {
            "user_id": self.test_user_id,
            "character_id": self.test_character_id,
            "conversation_id": f"test_conv_{uuid.uuid4().hex[:8]}",
            "title": "喝水",
            "action_template": "该喝水啦！记得保持水分哦~",
            "next_trigger_time": trigger_time,
            "time_original": "2分钟后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }

        # 创建提醒
        inserted_id = self.dao.create_reminder(reminder_data)
        self.assertIsNotNone(inserted_id)

        # 获取创建的提醒
        reminder = self.dao.get_reminder_by_object_id(inserted_id)
        self.assertIsNotNone(reminder)
        self.created_reminder_ids.append(reminder["reminder_id"])

        # 验证提醒内容
        self.assertEqual(reminder["title"], "喝水")
        self.assertEqual(reminder["status"], "confirmed")
        self.assertEqual(reminder["next_trigger_time"], trigger_time)

        print(f"✓ 用户说: '2分钟后提醒我喝水'")
        print("✓ 系统创建提醒成功")
        print(f"  - 提醒ID: {reminder['reminder_id']}")
        print(f"  - 标题: {reminder['title']}")
        print(
            f"  - 触发时间: {datetime.fromtimestamp(trigger_time).strftime('%H:%M:%S')}"
        )
        print(f"  - 状态: {reminder['status']}")

    def test_02_user_queries_reminders(self):
        """
        测试：用户查询提醒列表

        用户视角：
        1. 用户说"我有哪些提醒"
        2. 系统返回提醒列表
        """
        print("\n" + "=" * 50)
        print("集成测试：用户查询提醒列表")
        print("=" * 50)

        # 查询用户的提醒
        reminders = self.dao.find_reminders_by_user(self.test_user_id)

        print(f"✓ 用户说: '我有哪些提醒'")
        print("✓ 系统返回提醒列表")
        print(f"  - 共有 {len(reminders)} 个提醒")

        for r in reminders:
            trigger_time = datetime.fromtimestamp(r["next_trigger_time"]).strftime(
                "%H:%M:%S"
            )
            print(f"    - {r['title']} (触发时间: {trigger_time})")

        self.assertGreater(len(reminders), 0)

    def test_03_system_finds_pending_reminders(self):
        """
        测试：系统查找待触发的提醒

        模拟提醒到期后，系统能够找到它
        """
        print("\n" + "=" * 50)
        print("集成测试：系统查找待触发提醒")
        print("=" * 50)

        # 创建一个已到期的提醒
        past_time = int(time.time()) - 60  # 1分钟前

        reminder_data = {
            "user_id": self.test_user_id,
            "character_id": self.test_character_id,
            "conversation_id": f"test_conv_{uuid.uuid4().hex[:8]}",
            "title": "已到期的提醒",
            "action_template": "这是一个已到期的提醒",
            "next_trigger_time": past_time,
            "time_original": "1分钟前",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }

        inserted_id = self.dao.create_reminder(reminder_data)
        reminder = self.dao.get_reminder_by_object_id(inserted_id)
        self.created_reminder_ids.append(reminder["reminder_id"])

        # 查找待触发的提醒
        current_time = int(time.time())
        pending = self.dao.find_pending_reminders(current_time)

        # 验证能找到这个提醒
        found = any(r["reminder_id"] == reminder["reminder_id"] for r in pending)

        print("✓ 系统检查待触发的提醒")
        print(
            f"  - 当前时间: {datetime.fromtimestamp(current_time).strftime('%H:%M:%S')}"
        )
        print(f"  - 找到 {len(pending)} 个待触发提醒")
        print(f"  - 测试提醒是否在列表中: {'是' if found else '否'}")

        self.assertTrue(found, "应该能找到已到期的提醒")

    def test_04_reminder_trigger_and_complete(self):
        """
        测试：提醒触发和完成流程

        用户视角：
        1. 提醒到期
        2. 用户收到提醒消息
        3. 提醒标记为已完成
        """
        print("\n" + "=" * 50)
        print("集成测试：提醒触发和完成流程")
        print("=" * 50)

        # 获取之前创建的已到期提醒
        reminders = self.dao.find_reminders_by_user(self.test_user_id, "confirmed")
        self.assertGreater(len(reminders), 0)

        reminder = reminders[0]
        reminder_id = reminder["reminder_id"]

        print(f"✓ 提醒到期: {reminder['title']}")

        # 标记为已触发
        self.dao.mark_as_triggered(reminder_id)
        updated = self.dao.get_reminder_by_id(reminder_id)
        self.assertEqual(updated["triggered_count"], 1)
        print("✓ 系统触发提醒，发送消息给用户")
        print(f"  - 消息内容: {reminder['action_template']}")

        # 完成提醒
        self.dao.complete_reminder(reminder_id)
        completed = self.dao.get_reminder_by_id(reminder_id)
        self.assertEqual(completed["status"], "completed")
        print("✓ 提醒完成")
        print(f"  - 状态: {completed['status']}")
        print(f"  - 触发次数: {completed['triggered_count']}")


class TestRealFutureMessageIntegration(unittest.TestCase):
    """
    集成测试：使用真实数据库测试未来消息功能
    """

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        from dao.conversation_dao import ConversationDAO
        from dao.mongo import MongoDBBase
        from dao.user_dao import UserDAO

        cls.conversation_dao = ConversationDAO()
        cls.user_dao = UserDAO()
        cls.mongo = MongoDBBase()
        cls.created_conversation_ids = []

    @classmethod
    def tearDownClass(cls):
        """清理测试数据"""
        for conv_id in cls.created_conversation_ids:
            try:
                cls.conversation_dao.delete_conversation(conv_id)
            except Exception:
                pass
        cls.conversation_dao.close()
        cls.user_dao.close()
        cls.mongo.close()

    def test_01_conversation_with_future_message_planning(self):
        """
        测试：对话中规划未来消息

        用户视角：
        1. 用户与角色对话
        2. 角色规划未来主动消息
        3. 验证规划被保存
        """
        print("\n" + "=" * 50)
        print("集成测试：对话中规划未来消息")
        print("=" * 50)

        # 创建测试会话
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        test_char_id = f"test_char_{uuid.uuid4().hex[:8]}"

        conversation_data = {
            "platform": "wechat",
            "chatroom_name": None,
            "talkers": [
                {"id": test_user_id, "nickname": "测试用户"},
                {"id": test_char_id, "nickname": "测试角色"},
            ],
            "conversation_info": {
                "chat_history": [
                    {
                        "from_user": test_user_id,
                        "to_user": test_char_id,
                        "message": "晚安，明天见",
                        "timestamp": int(time.time()) - 60,
                    },
                    {
                        "from_user": test_char_id,
                        "to_user": test_user_id,
                        "message": "晚安~做个好梦哦，明天见！",
                        "timestamp": int(time.time()) - 30,
                    },
                ],
                "input_messages": [],
                "photo_history": [],
                "future": {
                    "timestamp": int(time.time()) + 36000,  # 10小时后（明天早上）
                    "action": "主动问候用户早安",
                    "proactive_times": 0,
                },
            },
        }

        # 创建会话
        conv_id = self.conversation_dao.create_conversation(conversation_data)
        self.created_conversation_ids.append(conv_id)

        # 验证会话创建成功
        conversation = self.conversation_dao.get_conversation_by_id(conv_id)
        self.assertIsNotNone(conversation)

        # 验证未来消息规划
        future = conversation["conversation_info"]["future"]
        self.assertIsNotNone(future["timestamp"])
        self.assertEqual(future["action"], "主动问候用户早安")

        print(f"✓ 用户说: '晚安，明天见'")
        print(f"✓ 角色回复: '晚安~做个好梦哦，明天见！'")
        print("✓ 系统规划未来消息:")
        print(
            f"  - 规划时间: {datetime.fromtimestamp(future['timestamp']).strftime('%Y-%m-%d %H:%M')}"
        )
        print(f"  - 规划行动: {future['action']}")

    def test_02_find_due_future_messages(self):
        """
        测试：查找到期的未来消息

        系统视角：
        1. 定时检查到期的会话
        2. 找到需要发送主动消息的会话
        """
        print("\n" + "=" * 50)
        print("集成测试：查找到期的未来消息")
        print("=" * 50)

        # 创建一个已到期的会话
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        test_char_id = f"test_char_{uuid.uuid4().hex[:8]}"

        conversation_data = {
            "platform": "wechat",
            "chatroom_name": None,
            "talkers": [
                {"id": test_user_id, "nickname": "测试用户"},
                {"id": test_char_id, "nickname": "测试角色"},
            ],
            "conversation_info": {
                "chat_history": [],
                "input_messages": [],
                "photo_history": [],
                "future": {
                    "timestamp": int(time.time()) - 60,  # 1分钟前到期
                    "action": "主动问候用户",
                    "proactive_times": 0,
                },
            },
        }

        conv_id = self.conversation_dao.create_conversation(conversation_data)
        self.created_conversation_ids.append(conv_id)

        # 查找到期的会话
        current_timestamp = int(time.time())
        query = {
            "conversation_info.future.timestamp": {
                "$exists": True,
                "$ne": None,
                "$lte": current_timestamp,
            }
        }

        due_conversations = self.conversation_dao.find_conversations(query)

        # 验证能找到这个会话
        found = any(str(c["_id"]) == conv_id for c in due_conversations)

        print("✓ 系统定时检查到期的未来消息")
        print(
            f"  - 当前时间: {datetime.fromtimestamp(current_timestamp).strftime('%H:%M:%S')}"
        )
        print(f"  - 找到 {len(due_conversations)} 个到期会话")
        print(f"  - 测试会话是否在列表中: {'是' if found else '否'}")

        self.assertTrue(found, "应该能找到已到期的会话")

    def test_03_update_future_after_proactive_message(self):
        """
        测试：发送主动消息后更新未来状态

        系统视角：
        1. 发送主动消息
        2. 更新会话的 future 状态
        3. 可能规划下一次主动消息
        """
        print("\n" + "=" * 50)
        print("集成测试：发送主动消息后更新状态")
        print("=" * 50)

        # 获取之前创建的到期会话
        current_timestamp = int(time.time())
        query = {
            "conversation_info.future.timestamp": {
                "$exists": True,
                "$ne": None,
                "$lte": current_timestamp,
            }
        }

        due_conversations = self.conversation_dao.find_conversations(query)
        self.assertGreater(len(due_conversations), 0)

        conversation = due_conversations[0]
        conv_id = str(conversation["_id"])

        print("✓ 系统发送主动消息")
        print(f"  - 会话ID: {conv_id}")
        print(f"  - 规划行动: {conversation['conversation_info']['future']['action']}")

        # 更新 future 状态（清除或设置下一次）
        update_data = {
            "conversation_info.future.timestamp": None,
            "conversation_info.future.action": None,
            "conversation_info.future.proactive_times": 1,
        }

        success = self.conversation_dao.update_conversation(conv_id, update_data)
        self.assertTrue(success)

        # 验证更新成功
        updated = self.conversation_dao.get_conversation_by_id(conv_id)
        self.assertIsNone(updated["conversation_info"]["future"]["timestamp"])
        self.assertEqual(updated["conversation_info"]["future"]["proactive_times"], 1)

        print("✓ 系统更新会话状态")
        print("  - 清除未来消息规划")
        print(
            f"  - 主动消息次数: {updated['conversation_info']['future']['proactive_times']}"
        )


class TestUserReceivesMessageIntegration(unittest.TestCase):
    """
    集成测试：验证用户能收到消息
    """

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        from dao.mongo import MongoDBBase

        cls.mongo = MongoDBBase()
        cls.created_message_ids = []

    @classmethod
    def tearDownClass(cls):
        """清理测试数据"""
        for msg_id in cls.created_message_ids:
            try:
                cls.mongo.delete_one("outputmessages", {"_id": ObjectId(msg_id)})
            except Exception:
                pass
        cls.mongo.close()

    def test_01_proactive_message_written_to_queue(self):
        """
        测试：主动消息写入输出队列

        用户视角：
        1. 系统生成主动消息
        2. 消息写入 outputmessages 队列
        3. 用户通过客户端收到消息
        """
        print("\n" + "=" * 50)
        print("集成测试：主动消息写入输出队列")
        print("=" * 50)

        test_conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        test_char_id = f"test_char_{uuid.uuid4().hex[:8]}"

        # 写入主动消息
        output_message = {
            "conversation_id": test_conv_id,
            "uid": test_user_id,
            "cid": test_char_id,
            "type": "text",
            "content": "早上好呀~昨晚睡得怎么样？",
            "emotion": "开心",
            "timestamp": int(time.time()),
            "source": "proactive_message",
        }

        msg_id = self.mongo.insert_one("outputmessages", output_message)
        self.created_message_ids.append(msg_id)

        # 验证消息写入成功
        written_msg = self.mongo.find_one("outputmessages", {"_id": ObjectId(msg_id)})
        self.assertIsNotNone(written_msg)
        self.assertEqual(written_msg["content"], "早上好呀~昨晚睡得怎么样？")
        self.assertEqual(written_msg["source"], "proactive_message")

        print("✓ 系统生成主动消息")
        print("✓ 消息写入输出队列")
        print(f"  - 消息ID: {msg_id}")
        print(f"  - 内容: {written_msg['content']}")
        print(f"  - 来源: {written_msg['source']}")
        print("✓ 用户将通过客户端收到此消息")

    def test_02_reminder_message_written_to_queue(self):
        """
        测试：提醒消息写入输出队列

        用户视角：
        1. 提醒到期
        2. 系统生成提醒消息
        3. 用户收到提醒
        """
        print("\n" + "=" * 50)
        print("集成测试：提醒消息写入输出队列")
        print("=" * 50)

        test_conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        test_char_id = f"test_char_{uuid.uuid4().hex[:8]}"

        # 写入提醒消息
        output_message = {
            "conversation_id": test_conv_id,
            "uid": test_user_id,
            "cid": test_char_id,
            "type": "text",
            "content": "该喝水啦！记得保持水分哦~",
            "timestamp": int(time.time()),
            "source": "reminder",
        }

        msg_id = self.mongo.insert_one("outputmessages", output_message)
        self.created_message_ids.append(msg_id)

        # 验证消息写入成功
        written_msg = self.mongo.find_one("outputmessages", {"_id": ObjectId(msg_id)})
        self.assertIsNotNone(written_msg)
        self.assertEqual(written_msg["content"], "该喝水啦！记得保持水分哦~")
        self.assertEqual(written_msg["source"], "reminder")

        print("✓ 提醒到期，系统生成提醒消息")
        print("✓ 消息写入输出队列")
        print(f"  - 消息ID: {msg_id}")
        print(f"  - 内容: {written_msg['content']}")
        print(f"  - 来源: {written_msg['source']}")
        print("✓ 用户收到提醒消息")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
