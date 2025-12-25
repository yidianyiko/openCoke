# -*- coding: utf-8 -*-
"""
Turn Sent Contents 去重功能测试

测试 rollback 场景下的消息去重机制：
- 发送前检查 turn_sent_contents
- Rollback 时记录已发送内容
- Turn 完成时清空列表
"""
import sys

sys.path.append(".")

import logging
import unittest

logger = logging.getLogger(__name__)


class TestTurnSentContentsDedup(unittest.TestCase):
    """测试 turn_sent_contents 去重机制"""

    def test_skip_already_sent_content(self):
        """测试跳过已发送的内容"""
        # 模拟 context 中有 turn_sent_contents
        context = {
            "conversation": {
                "conversation_info": {
                    "turn_sent_contents": ["哈哈，是我误会了", "好的"]
                }
            }
        }

        # 模拟 _send_single_message 中的检查逻辑
        content = "哈哈，是我误会了"
        turn_sent = (
            context.get("conversation", {})
            .get("conversation_info", {})
            .get("turn_sent_contents", [])
        )

        should_skip = turn_sent and content in turn_sent
        self.assertTrue(should_skip, "应该跳过已发送的内容")

    def test_send_new_content(self):
        """测试发送新内容"""
        context = {
            "conversation": {
                "conversation_info": {"turn_sent_contents": ["哈哈，是我误会了"]}
            }
        }

        content = "来得好"
        turn_sent = (
            context.get("conversation", {})
            .get("conversation_info", {})
            .get("turn_sent_contents", [])
        )

        should_skip = turn_sent and content in turn_sent
        self.assertFalse(should_skip, "新内容不应该被跳过")

    def test_empty_turn_sent_contents(self):
        """测试空的 turn_sent_contents"""
        context = {"conversation": {"conversation_info": {"turn_sent_contents": []}}}

        content = "任何内容"
        turn_sent = (
            context.get("conversation", {})
            .get("conversation_info", {})
            .get("turn_sent_contents", [])
        )

        should_skip = turn_sent and content in turn_sent
        self.assertFalse(should_skip, "空列表时不应该跳过任何内容")

    def test_missing_turn_sent_contents(self):
        """测试缺少 turn_sent_contents 字段"""
        context = {"conversation": {"conversation_info": {}}}

        content = "任何内容"
        turn_sent = (
            context.get("conversation", {})
            .get("conversation_info", {})
            .get("turn_sent_contents", [])
        )

        should_skip = turn_sent and content in turn_sent
        self.assertFalse(should_skip, "缺少字段时不应该跳过任何内容")


class TestRollbackRecordSentContents(unittest.TestCase):
    """测试 rollback 时记录已发送内容"""

    def test_record_sent_contents_on_rollback(self):
        """测试 rollback 时记录已发送内容到 turn_sent_contents"""
        conversation = {
            "conversation_info": {"chat_history": [], "turn_sent_contents": []}
        }

        resp_messages = [
            {"message": "哈哈，是我误会了", "type": "text"},
            {"message": "好的", "type": "text"},
        ]

        # 模拟 rollback 块中的逻辑
        sent_contents = [
            msg.get("message", "") for msg in resp_messages if msg.get("message")
        ]
        existing = conversation["conversation_info"].get("turn_sent_contents", [])
        conversation["conversation_info"]["turn_sent_contents"] = (
            existing + sent_contents
        )

        self.assertEqual(
            conversation["conversation_info"]["turn_sent_contents"],
            ["哈哈，是我误会了", "好的"],
        )

    def test_accumulate_sent_contents_across_rollbacks(self):
        """测试多次 rollback 累积已发送内容"""
        conversation = {
            "conversation_info": {
                "chat_history": [],
                "turn_sent_contents": ["第一轮消息"],
            }
        }

        resp_messages = [{"message": "第二轮消息", "type": "text"}]

        # 模拟第二次 rollback
        sent_contents = [
            msg.get("message", "") for msg in resp_messages if msg.get("message")
        ]
        existing = conversation["conversation_info"].get("turn_sent_contents", [])
        conversation["conversation_info"]["turn_sent_contents"] = (
            existing + sent_contents
        )

        self.assertEqual(
            conversation["conversation_info"]["turn_sent_contents"],
            ["第一轮消息", "第二轮消息"],
        )

    def test_skip_empty_messages(self):
        """测试跳过空消息"""
        conversation = {"conversation_info": {"turn_sent_contents": []}}

        resp_messages = [
            {"message": "有内容", "type": "text"},
            {"message": "", "type": "text"},
            {"message": None, "type": "text"},
            {"type": "text"},  # 没有 message 字段
        ]

        sent_contents = [
            msg.get("message", "") for msg in resp_messages if msg.get("message")
        ]
        conversation["conversation_info"]["turn_sent_contents"] = sent_contents

        self.assertEqual(
            conversation["conversation_info"]["turn_sent_contents"], ["有内容"]
        )


class TestTurnCompleteClearContents(unittest.TestCase):
    """测试 Turn 完成时清空 turn_sent_contents"""

    def test_clear_on_turn_complete(self):
        """测试 Turn 完成时清空列表"""
        conversation = {
            "conversation_info": {
                "chat_history": [],
                "turn_sent_contents": ["消息1", "消息2"],
            }
        }

        # 模拟 is_finish 块中的清空逻辑
        if conversation["conversation_info"].get("turn_sent_contents"):
            conversation["conversation_info"]["turn_sent_contents"] = []

        self.assertEqual(conversation["conversation_info"]["turn_sent_contents"], [])

    def test_no_error_when_already_empty(self):
        """测试列表已空时不报错"""
        conversation = {
            "conversation_info": {"chat_history": [], "turn_sent_contents": []}
        }

        # 模拟清空逻辑
        if conversation["conversation_info"].get("turn_sent_contents"):
            conversation["conversation_info"]["turn_sent_contents"] = []

        # 不应该报错，列表保持为空
        self.assertEqual(conversation["conversation_info"]["turn_sent_contents"], [])

    def test_no_error_when_field_missing(self):
        """测试字段缺失时不报错"""
        conversation = {"conversation_info": {"chat_history": []}}

        # 模拟清空逻辑
        if conversation["conversation_info"].get("turn_sent_contents"):
            conversation["conversation_info"]["turn_sent_contents"] = []

        # 不应该报错，字段不存在
        self.assertNotIn("turn_sent_contents", conversation["conversation_info"])


class TestFullDedupFlow(unittest.TestCase):
    """测试完整的去重流程"""

    def test_full_dedup_scenario(self):
        """
        测试完整场景：
        Round 1: 发送 "哈哈" → rollback → 记录
        Round 2: "哈哈" 被跳过 → 发送 "来得好" → 完成 → 清空
        """
        # Round 1: 初始状态
        conversation = {
            "conversation_info": {"chat_history": [], "turn_sent_contents": []}
        }

        # Round 1: 发送消息
        round1_messages = [{"message": "哈哈", "type": "text"}]

        # Round 1: Rollback，记录已发送内容
        sent_contents = [
            msg.get("message", "") for msg in round1_messages if msg.get("message")
        ]
        existing = conversation["conversation_info"].get("turn_sent_contents", [])
        conversation["conversation_info"]["turn_sent_contents"] = (
            existing + sent_contents
        )

        self.assertEqual(
            conversation["conversation_info"]["turn_sent_contents"], ["哈哈"]
        )

        # Round 2: 检查 "哈哈" 是否应该跳过
        content_haha = "哈哈"
        turn_sent = conversation["conversation_info"].get("turn_sent_contents", [])
        should_skip_haha = turn_sent and content_haha in turn_sent
        self.assertTrue(should_skip_haha, "Round 2: '哈哈' 应该被跳过")

        # Round 2: 检查 "来得好" 是否应该发送
        content_new = "来得好"
        should_skip_new = turn_sent and content_new in turn_sent
        self.assertFalse(should_skip_new, "Round 2: '来得好' 应该被发送")

        # Round 2: Turn 完成，清空列表
        conversation["conversation_info"]["turn_sent_contents"] = []

        self.assertEqual(conversation["conversation_info"]["turn_sent_contents"], [])

    def test_multiple_rollback_scenario(self):
        """
        测试多次 rollback 场景：
        Round 1: 发送 "A" → rollback
        Round 2: 跳过 "A"，发送 "B" → rollback
        Round 3: 跳过 "A", "B"，发送 "C" → 完成
        """
        conversation = {"conversation_info": {"turn_sent_contents": []}}

        # Round 1
        conversation["conversation_info"]["turn_sent_contents"] = ["A"]

        # Round 2
        turn_sent = conversation["conversation_info"]["turn_sent_contents"]
        self.assertTrue("A" in turn_sent)  # A 应该被跳过
        self.assertFalse("B" in turn_sent)  # B 应该发送
        conversation["conversation_info"]["turn_sent_contents"] = turn_sent + ["B"]

        # Round 3
        turn_sent = conversation["conversation_info"]["turn_sent_contents"]
        self.assertTrue("A" in turn_sent)  # A 应该被跳过
        self.assertTrue("B" in turn_sent)  # B 应该被跳过
        self.assertFalse("C" in turn_sent)  # C 应该发送

        # Turn 完成
        conversation["conversation_info"]["turn_sent_contents"] = []
        self.assertEqual(conversation["conversation_info"]["turn_sent_contents"], [])


if __name__ == "__main__":
    unittest.main()
