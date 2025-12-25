# -*- coding: utf-8 -*-
"""
ProactiveMessageTriggerService 单元测试

测试主动消息触发服务的实现：
- check_and_trigger() 方法
- _get_due_conversations() 方法
- _trigger_proactive_message() 方法
- 消息写入逻辑

Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""
import sys

sys.path.append(".")

import time
import unittest
from unittest.mock import MagicMock, patch


class TestProactiveMessageTriggerServiceInstantiation(unittest.TestCase):
    """测试 ProactiveMessageTriggerService 实例化"""

    def test_service_can_be_instantiated(self):
        """测试服务可以被实例化"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        # 使用 Mock DAO
        mock_conversation_dao = MagicMock()
        mock_user_dao = MagicMock()
        mock_mongo = MagicMock()

        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=mock_user_dao,
            mongo=mock_mongo,
        )

        self.assertIsNotNone(service)
        self.assertEqual(service.conversation_dao, mock_conversation_dao)
        self.assertEqual(service.user_dao, mock_user_dao)
        self.assertEqual(service.mongo, mock_mongo)

    def test_service_has_required_methods(self):
        """测试服务包含所有必需方法"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_dao = MagicMock()
        mock_mongo = MagicMock()
        service = ProactiveMessageTriggerService(
            conversation_dao=mock_dao, user_dao=mock_dao, mongo=mock_mongo
        )

        self.assertTrue(hasattr(service, "check_and_trigger"))
        self.assertTrue(hasattr(service, "_get_due_conversations"))
        self.assertTrue(hasattr(service, "_trigger_proactive_message"))
        self.assertTrue(hasattr(service, "_write_output_messages"))
        self.assertTrue(hasattr(service, "_update_conversation_future"))


class TestGetDueConversations(unittest.TestCase):
    """测试 _get_due_conversations 方法 (Requirement 6.1)"""

    def test_get_due_conversations_returns_list(self):
        """测试返回列表类型"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.return_value = []

        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=MagicMock(),
            mongo=MagicMock(),
        )

        result = service._get_due_conversations()

        self.assertIsInstance(result, list)

    def test_get_due_conversations_queries_correct_filter(self):
        """测试查询使用正确的过滤条件"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.return_value = []

        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=MagicMock(),
            mongo=MagicMock(),
        )

        service._get_due_conversations()

        # 验证调用了 find_conversations
        mock_conversation_dao.find_conversations.assert_called_once()

        # 获取调用参数
        call_args = mock_conversation_dao.find_conversations.call_args
        query = call_args[0][0]

        # 验证查询条件包含 future.timestamp
        self.assertIn("conversation_info.future.timestamp", query)

    def test_get_due_conversations_handles_exception(self):
        """测试异常处理"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.side_effect = Exception(
            "Database error"
        )

        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=MagicMock(),
            mongo=MagicMock(),
        )

        # 应该返回空列表而不是抛出异常
        result = service._get_due_conversations()

        self.assertEqual(result, [])


class TestCheckAndTrigger(unittest.TestCase):
    """测试 check_and_trigger 方法 (Requirements 6.1, 6.2)"""

    def test_check_and_trigger_returns_list(self):
        """测试返回列表类型"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.return_value = []

        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=MagicMock(),
            mongo=MagicMock(),
        )

        result = service.check_and_trigger()

        self.assertIsInstance(result, list)

    def test_check_and_trigger_processes_due_conversations(self):
        """测试处理到期会话"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        # 创建模拟会话 - 使用 talkers 格式
        mock_conversation = {
            "_id": "conv_123",
            "talkers": [
                {"id": "user_456", "nickname": "测试用户"},
                {"id": "char_789", "nickname": "测试角色"},
            ],
            "conversation_info": {
                "future": {"timestamp": int(time.time()) - 100, "action": "测试行动"}
            },
        }

        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.return_value = [mock_conversation]
        mock_conversation_dao.update_conversation.return_value = True

        mock_user_dao = MagicMock()
        # 第一次调用返回普通用户，第二次返回角色
        mock_user_dao.get_user_by_id.side_effect = [
            {
                "_id": "user_456",
                "is_character": False,
                "platforms": {"wechat": {"nickname": "测试用户"}},
            },
            {
                "_id": "char_789",
                "is_character": True,
                "platforms": {"wechat": {"nickname": "测试角色"}},
            },
            {
                "_id": "user_456",
                "is_character": False,
                "platforms": {"wechat": {"nickname": "测试用户"}},
            },
            {
                "_id": "char_789",
                "is_character": True,
                "platforms": {"wechat": {"nickname": "测试角色"}},
            },
        ]

        mock_mongo = MagicMock()
        mock_mongo.find_one.return_value = None  # No relation found

        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=mock_user_dao,
            mongo=mock_mongo,
        )

        # Mock workflow
        with patch(
            "agent.agno_agent.workflows.future_message_workflow.FutureMessageWorkflow"
        ) as mock_workflow_class:
            mock_workflow = MagicMock()
            mock_workflow.run.return_value = {
                "content": {"MultiModalResponses": []},
                "session_state": {
                    "conversation": {"conversation_info": {"future": {}}}
                },
            }
            mock_workflow_class.return_value = mock_workflow

            result = service.check_and_trigger()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["conversation_id"], "conv_123")


class TestBuildSessionState(unittest.TestCase):
    """测试 _build_session_state 方法"""

    def test_build_session_state_structure(self):
        """测试 session_state 结构"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        service = ProactiveMessageTriggerService(
            conversation_dao=MagicMock(), user_dao=MagicMock(), mongo=MagicMock()
        )

        user = {"_id": "user_123", "name": "测试用户"}
        character = {"_id": "char_456", "name": "测试角色"}
        conversation = {"_id": "conv_789", "conversation_info": {}}
        relation = None

        result = service._build_session_state(user, character, conversation, relation)

        # 验证结构
        self.assertIn("user", result)
        self.assertIn("character", result)
        self.assertIn("conversation", result)
        self.assertIn("relation", result)
        self.assertIn("context_retrieve", result)

        # 验证 relation 有默认值
        self.assertIn("relationship", result["relation"])
        self.assertIn("closeness", result["relation"]["relationship"])

    def test_build_session_state_with_relation(self):
        """测试带关系数据的 session_state"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        service = ProactiveMessageTriggerService(
            conversation_dao=MagicMock(), user_dao=MagicMock(), mongo=MagicMock()
        )

        user = {"_id": "user_123"}
        character = {"_id": "char_456"}
        conversation = {"_id": "conv_789"}
        relation = {"relationship": {"closeness": 80, "trustness": 70}}

        result = service._build_session_state(user, character, conversation, relation)

        # 验证使用传入的 relation
        self.assertEqual(result["relation"]["relationship"]["closeness"], 80)


class TestWriteOutputMessages(unittest.TestCase):
    """测试 _write_output_messages 方法 (Requirement 6.3)"""

    def test_write_output_messages_calls_mongo(self):
        """测试写入消息调用 MongoDB"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_mongo = MagicMock()

        service = ProactiveMessageTriggerService(
            conversation_dao=MagicMock(), user_dao=MagicMock(), mongo=mock_mongo
        )

        multimodal_responses = [
            {"type": "text", "content": "你好！"},
            {"type": "text", "content": "在干嘛呢？"},
        ]

        service._write_output_messages(
            conversation_id="conv_123",
            user_id="user_456",
            character_id="char_789",
            multimodal_responses=multimodal_responses,
        )

        # 验证调用了 insert_one 两次
        self.assertEqual(mock_mongo.insert_one.call_count, 2)

    def test_write_output_messages_skips_empty_content(self):
        """测试跳过空内容"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_mongo = MagicMock()

        service = ProactiveMessageTriggerService(
            conversation_dao=MagicMock(), user_dao=MagicMock(), mongo=mock_mongo
        )

        multimodal_responses = [
            {"type": "text", "content": ""},  # 空内容
            {"type": "text", "content": "有内容"},
        ]

        service._write_output_messages(
            conversation_id="conv_123",
            user_id="user_456",
            character_id="char_789",
            multimodal_responses=multimodal_responses,
        )

        # 只应该调用一次（跳过空内容）
        self.assertEqual(mock_mongo.insert_one.call_count, 1)


class TestUpdateConversationFuture(unittest.TestCase):
    """测试 _update_conversation_future 方法 (Requirement 6.4)"""

    def test_update_conversation_future_calls_dao(self):
        """测试更新会话调用 DAO"""
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService,
        )

        mock_conversation_dao = MagicMock()

        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=MagicMock(),
            mongo=MagicMock(),
        )

        updated_session_state = {
            "conversation": {
                "conversation_info": {
                    "future": {
                        "timestamp": 12345,
                        "action": "下次行动",
                        "proactive_times": 2,
                    }
                }
            }
        }

        service._update_conversation_future(
            conversation_id="conv_123", updated_session_state=updated_session_state
        )

        # 验证调用了 update_conversation
        mock_conversation_dao.update_conversation.assert_called_once()

        # 验证更新数据
        call_args = mock_conversation_dao.update_conversation.call_args
        self.assertEqual(call_args[0][0], "conv_123")


class TestServiceExports(unittest.TestCase):
    """测试服务模块导出"""

    def test_can_import_from_services_module(self):
        """测试可以从 services 模块导入"""
        try:
            from agent.agno_agent.services import ProactiveMessageTriggerService

            self.assertIsNotNone(ProactiveMessageTriggerService)
        except ImportError as e:
            self.fail(f"Failed to import: {e}")


if __name__ == "__main__":
    unittest.main()
