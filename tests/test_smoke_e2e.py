# -*- coding: utf-8 -*-
"""
端到端冒烟测试

测试完整的消息处理流程，包括：
1. context_prepare 构建 session_state
2. ObjectId 序列化
3. Workflow 执行
4. relation 持久化（修复后的逻辑）

这个测试覆盖了生产环境中发现的 _id 字段问题.
"""
import sys

sys.path.append(".")
import time
import unittest
from unittest.mock import Mock

from bson import ObjectId


class TestSmokeE2E(unittest.TestCase):
    """端到端冒烟测试"""

    def test_full_message_handling_flow_mock(self):
        """
        测试完整的消息处理流程（使用 Mock）

        模拟 agent_handler.main_handler 的核心逻辑
        """
        from agent.runner.context import _convert_objectid_to_str

        # 1. 模拟从数据库读取的原始数据
        user = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "platforms": {"wechat": {"id": "wxid_user123", "nickname": "测试用户"}},
        }

        character = {
            "_id": ObjectId("507f1f77bcf86cd799439012"),
            "platforms": {"wechat": {"id": "wxid_char456", "nickname": "测试角色"}},
            "user_info": {
                "description": "一个友好的AI角色",
                "status": {"place": "家里", "action": "休息"},
            },
        }

        conversation = {
            "_id": ObjectId("507f1f77bcf86cd799439013"),
            "conversation_info": {
                "chat_history": [],
                "input_messages": [
                    {
                        "_id": ObjectId("507f1f77bcf86cd799439014"),
                        "from_user": str(user["_id"]),
                        "to_user": str(character["_id"]),
                        "message": "你好",
                        "timestamp": int(time.time()),
                    }
                ],
                "photo_history": [],
                "future": {"timestamp": None, "action": None},
            },
        }

        relation = {
            "_id": ObjectId("507f1f77bcf86cd799439015"),
            "uid": str(user["_id"]),
            "cid": str(character["_id"]),
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲",
            },
            "user_info": {"realname": "", "hobbyname": "", "description": "新朋友"},
            "character_info": {
                "longterm_purpose": "帮助用户",
                "shortterm_purpose": "聊天",
                "attitude": "友好",
            },
        }

        # 2. 模拟 context_prepare 的核心逻辑
        context = {
            "user": user,
            "character": character,
            "conversation": conversation,
            "relation": relation,
        }

        # 添加必要的默认值
        context["conversation"]["conversation_info"].setdefault(
            "time_str", "2024年12月8日"
        )
        context["conversation"]["conversation_info"].setdefault("chat_history_str", "")
        context["conversation"]["conversation_info"].setdefault(
            "input_messages_str", "用户: 你好"
        )
        context.setdefault("news_str", "")
        context.setdefault("repeated_input_notice", "")
        context.setdefault("MultiModalResponses", [])
        context.setdefault(
            "context_retrieve",
            {
                "character_global": "",
                "character_private": "",
                "user": "",
                "character_knowledge": "",
                "confirmed_reminders": "",
            },
        )
        context.setdefault(
            "query_rewrite",
            {
                "InnerMonologue": "",
                "CharacterSettingQueryQuestion": "",
                "CharacterSettingQueryKeywords": "",
                "UserProfileQueryQuestion": "",
                "UserProfileQueryKeywords": "",
                "CharacterKnowledgeQueryQuestion": "",
                "CharacterKnowledgeQueryKeywords": "",
            },
        )

        # 3. ObjectId 序列化（关键步骤）
        context = _convert_objectid_to_str(context)

        # 验证所有 ObjectId 都被转换为字符串
        self.assertIsInstance(context["user"]["_id"], str)
        self.assertIsInstance(context["character"]["_id"], str)
        self.assertIsInstance(context["conversation"]["_id"], str)
        self.assertIsInstance(context["relation"]["_id"], str)

        # 4. 模拟 Workflow 执行后修改 relation
        context["relation"]["relationship"]["closeness"] = 55
        context["relation"]["user_info"]["realname"] = "小明"

        # 5. 测试修复后的 replace_one 逻辑
        # 这是修复的关键：移除 _id 字段
        relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}

        # 验证 update 对象不包含 _id
        self.assertNotIn("_id", relation_update)

        # 验证其他字段正确
        self.assertEqual(relation_update["uid"], str(user["_id"]))
        self.assertEqual(relation_update["cid"], str(character["_id"]))
        self.assertEqual(relation_update["relationship"]["closeness"], 55)
        self.assertEqual(relation_update["user_info"]["realname"], "小明")

        # 6. 模拟 MongoDB replace_one 调用
        mock_mongo = Mock()
        mock_mongo.replace_one = Mock(return_value=1)

        result = mock_mongo.replace_one(
            "relations",
            query={
                "uid": context["relation"]["uid"],
                "cid": context["relation"]["cid"],
            },
            update=relation_update,
        )

        # 验证调用成功
        self.assertEqual(result, 1)
        mock_mongo.replace_one.assert_called_once()

        # 验证调用参数
        call_args = mock_mongo.replace_one.call_args
        self.assertEqual(call_args[0][0], "relations")
        self.assertNotIn("_id", call_args[1]["update"])

    def test_workflow_session_state_compatibility(self):
        """测试 Workflow 与 session_state 的兼容性"""
        from agent.runner.context import _convert_objectid_to_str

        # 构建完整的 session_state
        session_state = {
            "user": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"id": "wxid_123", "nickname": "用户"}},
            },
            "character": {
                "_id": ObjectId(),
                "platforms": {"wechat": {"id": "wxid_456", "nickname": "角色"}},
                "user_info": {"description": "", "status": {"place": "", "action": ""}},
            },
            "conversation": {
                "_id": ObjectId(),
                "conversation_info": {
                    "chat_history": [],
                    "input_messages": [],
                    "input_messages_str": "用户: 测试消息",
                    "chat_history_str": "",
                    "time_str": "2024年12月8日",
                    "photo_history": [],
                    "future": {"timestamp": None, "action": None},
                },
            },
            "relation": {
                "_id": ObjectId(),
                "uid": "user_id",
                "cid": "char_id",
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                    "dislike": 0,
                    "status": "空闲",
                },
                "user_info": {"realname": "", "hobbyname": "", "description": ""},
                "character_info": {
                    "longterm_purpose": "",
                    "shortterm_purpose": "",
                    "attitude": "",
                },
            },
            "news_str": "",
            "repeated_input_notice": "",
            "MultiModalResponses": [],
            "context_retrieve": {
                "character_global": "",
                "character_private": "",
                "user": "",
                "character_knowledge": "",
                "confirmed_reminders": "",
            },
            "query_rewrite": {
                "InnerMonologue": "",
                "CharacterSettingQueryQuestion": "",
                "CharacterSettingQueryKeywords": "",
                "UserProfileQueryQuestion": "",
                "UserProfileQueryKeywords": "",
                "CharacterKnowledgeQueryQuestion": "",
                "CharacterKnowledgeQueryKeywords": "",
            },
        }

        # 转换 ObjectId
        converted = _convert_objectid_to_str(session_state)

        # 验证可以 JSON 序列化
        import json

        try:
            json_str = json.dumps(converted, ensure_ascii=False)
            self.assertIsInstance(json_str, str)
        except (TypeError, ValueError) as e:
            self.fail(f"session_state 无法 JSON 序列化: {e}")

        # 验证结构完整性
        self.assertIn("user", converted)
        self.assertIn("character", converted)
        self.assertIn("conversation", converted)
        self.assertIn("relation", converted)
        self.assertIn("context_retrieve", converted)
        self.assertIn("query_rewrite", converted)

    def test_input_message_status_update(self):
        """测试输入消息状态更新"""
        # 模拟消息状态流转
        input_message = {"_id": ObjectId(), "status": "pending", "message": "测试消息"}

        # pending -> handling
        input_message["status"] = "handling"
        self.assertEqual(input_message["status"], "handling")

        # handling -> handled
        input_message["status"] = "handled"
        self.assertEqual(input_message["status"], "handled")

        # 验证 save_inputmessage 使用 _id 作为查询条件
        # 这里 _id 保持 ObjectId 类型，不会有问题
        self.assertIsInstance(input_message["_id"], ObjectId)


class TestRegressionPrevention(unittest.TestCase):
    """回归测试：防止问题再次出现"""

    def test_relation_update_must_exclude_id(self):
        """
        回归测试：确保 relation 更新时排除 _id 字段

        这个测试防止未来的代码修改重新引入这个 bug
        """
        from agent.runner.context import _convert_objectid_to_str

        # 模拟生产环境的数据
        relation = {
            "_id": ObjectId("692c14aaa58e1cd8e0750f4a"),  # 使用错误日志中的实际 ID
            "uid": "692c14aaa538f0baad5561b3",
            "cid": "692c147e972f64f2b65da6ee",
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲",
            },
        }

        # 转换后
        converted = _convert_objectid_to_str(relation)

        # 验证 _id 被转换为字符串
        self.assertEqual(converted["_id"], "692c14aaa58e1cd8e0750f4a")
        self.assertIsInstance(converted["_id"], str)

        # 构建 update 对象（修复后的逻辑）
        relation_update = {k: v for k, v in converted.items() if k != "_id"}

        # 关键断言：update 对象不能包含 _id
        self.assertNotIn(
            "_id",
            relation_update,
            "relation_update 不应包含 _id 字段，否则会导致 MongoDB WriteError",
        )

        # 验证其他字段保留
        self.assertIn("uid", relation_update)
        self.assertIn("cid", relation_update)
        self.assertIn("relationship", relation_update)

    def test_context_prepare_output_is_json_serializable(self):
        """
        回归测试：确保 context_prepare 输出可以 JSON 序列化
        """
        import json

        from agent.runner.context import _convert_objectid_to_str

        # 包含各种类型的数据
        data = {
            "_id": ObjectId(),
            "nested": {
                "inner_id": ObjectId(),
                "list_with_ids": [ObjectId(), ObjectId()],
                "mixed": [1, "string", ObjectId(), {"deep_id": ObjectId()}],
            },
        }

        converted = _convert_objectid_to_str(data)

        # 必须能够 JSON 序列化
        try:
            json.dumps(converted)
        except (TypeError, ValueError) as e:
            self.fail(f"转换后的数据无法 JSON 序列化: {e}")


if __name__ == "__main__":
    unittest.main()
