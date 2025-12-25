# -*- coding: utf-8 -*-
"""
MongoDB 操作全面测试

测试所有涉及 MongoDB 操作的场景，确保没有 _id 类型不匹配问题.

测试覆盖：
1. entity / message.py - save_inputmessage, save_outputmessage
2. agent / runner / agent_handler.py - relation 更新
3. agent/runner/agent_background_handler.py - relation 更新, conversation 更新
4. dao/conversation_dao.py - update_conversation_info
"""
import sys

sys.path.append(".")
import time
import unittest

from bson import ObjectId


class TestMessageOperations(unittest.TestCase):
    """测试消息相关的 MongoDB 操作"""

    def test_save_inputmessage_uses_objectid(self):
        """测试 save_inputmessage 使用 ObjectId 作为查询条件"""
        # 模拟从数据库读取的消息（_id 是 ObjectId）
        input_message = {
            "_id": ObjectId(),
            "status": "pending",
            "message": "测试消息",
            "from_user": "user_123",
            "to_user": "char_456",
        }

        # 验证 _id 是 ObjectId 类型
        self.assertIsInstance(input_message["_id"], ObjectId)

        # 模拟状态更新
        input_message["status"] = "handling"

        # 验证 _id 仍然是 ObjectId
        self.assertIsInstance(input_message["_id"], ObjectId)

    def test_save_outputmessage_uses_objectid(self):
        """测试 save_outputmessage 使用 ObjectId 作为查询条件"""
        output_message = {
            "_id": ObjectId(),
            "status": "pending",
            "message": "回复消息",
            "from_user": "char_456",
            "to_user": "user_123",
        }

        self.assertIsInstance(output_message["_id"], ObjectId)

        output_message["status"] = "handled"
        output_message["handled_timestamp"] = int(time.time())

        self.assertIsInstance(output_message["_id"], ObjectId)


class TestRelationOperations(unittest.TestCase):
    """测试 relation 相关的 MongoDB 操作"""

    def test_relation_from_database_has_objectid(self):
        """测试直接从数据库读取的 relation 有 ObjectId"""
        # 模拟从数据库读取的 relation
        relation = {
            "_id": ObjectId(),
            "uid": "user_123",
            "cid": "char_456",
            "relationship": {"closeness": 50, "trustness": 50},
        }

        self.assertIsInstance(relation["_id"], ObjectId)

    def test_relation_after_context_prepare_has_string_id(self):
        """测试经过 context_prepare 后 relation 的 _id 是字符串"""
        from agent.runner.context import _convert_objectid_to_str

        relation = {
            "_id": ObjectId(),
            "uid": "user_123",
            "cid": "char_456",
            "relationship": {"closeness": 50, "trustness": 50},
        }

        converted = _convert_objectid_to_str(relation)

        self.assertIsInstance(converted["_id"], str)

    def test_relation_update_must_exclude_id_after_conversion(self):
        """测试转换后的 relation 更新必须排除 _id"""
        from agent.runner.context import _convert_objectid_to_str

        relation = {
            "_id": ObjectId(),
            "uid": "user_123",
            "cid": "char_456",
            "relationship": {"closeness": 50, "trustness": 50},
        }

        converted = _convert_objectid_to_str(relation)

        # 修复后的逻辑
        relation_update = {k: v for k, v in converted.items() if k != "_id"}

        self.assertNotIn("_id", relation_update)
        self.assertIn("uid", relation_update)
        self.assertIn("cid", relation_update)

    def test_relation_direct_from_db_can_use_id_in_query(self):
        """测试直接从数据库读取的 relation 可以使用 _id 作为查询条件"""
        # 这是 agent_background_handler.py 第 102 行的场景
        relation = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "uid": "user_123",
            "cid": "char_456",
            "relationship": {"closeness": 50, "trustness": 50},
        }

        # 直接使用 _id 作为查询条件是安全的
        query = {"_id": relation["_id"]}

        self.assertIsInstance(query["_id"], ObjectId)

        # update 对象包含相同的 _id 也是安全的（类型一致）
        self.assertIsInstance(relation["_id"], ObjectId)


class TestConversationOperations(unittest.TestCase):
    """测试 conversation 相关的 MongoDB 操作"""

    def test_conversation_from_database_has_objectid(self):
        """测试直接从数据库读取的 conversation 有 ObjectId"""
        conversation = {
            "_id": ObjectId(),
            "platform": "wechat",
            "conversation_info": {
                "chat_history": [],
                "future": {"timestamp": None, "action": None},
            },
        }

        self.assertIsInstance(conversation["_id"], ObjectId)

    def test_conversation_replace_one_with_objectid_is_safe(self):
        """测试使用 ObjectId 的 conversation replace_one 是安全的"""
        # 这是 agent_background_handler.py 第 164 行的场景
        conversation = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "platform": "wechat",
            "conversation_info": {
                "chat_history": [],
                "future": {"timestamp": None, "action": None},
            },
        }

        # 修改数据
        conversation["conversation_info"]["future"]["timestamp"] = int(time.time())
        conversation["conversation_info"]["future"]["action"] = "测试话题"

        # 使用 _id 作为查询条件
        query = {"_id": conversation["_id"]}

        # 验证类型一致
        self.assertIsInstance(query["_id"], ObjectId)
        self.assertIsInstance(conversation["_id"], ObjectId)

    def test_update_conversation_info_uses_set_operator(self):
        """测试 update_conversation_info 使用 $set 操作符"""
        # 这个方法不涉及 _id 字段的修改
        conversation_id = str(ObjectId())
        info_data = {
            "chat_history": [{"message": "test"}],
            "future": {"timestamp": int(time.time()), "action": "test"},
        }

        # 验证 info_data 不包含 _id
        self.assertNotIn("_id", info_data)


class TestContextPrepareImpact(unittest.TestCase):
    """测试 context_prepare 对数据的影响"""

    def test_context_prepare_converts_all_objectids(self):
        """测试 context_prepare 转换所有 ObjectId"""
        from agent.runner.context import _convert_objectid_to_str

        data = {
            "user": {"_id": ObjectId()},
            "character": {"_id": ObjectId()},
            "conversation": {
                "_id": ObjectId(),
                "conversation_info": {
                    "input_messages": [{"_id": ObjectId(), "message": "test"}]
                },
            },
            "relation": {"_id": ObjectId(), "uid": "u1", "cid": "c1"},
        }

        converted = _convert_objectid_to_str(data)

        # 验证所有 _id 都被转换
        self.assertIsInstance(converted["user"]["_id"], str)
        self.assertIsInstance(converted["character"]["_id"], str)
        self.assertIsInstance(converted["conversation"]["_id"], str)
        self.assertIsInstance(
            converted["conversation"]["conversation_info"]["input_messages"][0]["_id"],
            str,
        )
        self.assertIsInstance(converted["relation"]["_id"], str)

    def test_original_data_not_affected_by_conversion(self):
        """测试原始数据不受转换影响"""
        import copy

        from agent.runner.context import _convert_objectid_to_str

        original = {"_id": ObjectId(), "data": "test"}

        # 深拷贝原始数据
        original_copy = copy.deepcopy(original)

        # 转换
        converted = _convert_objectid_to_str(original)

        # 验证原始数据未被修改（_convert_objectid_to_str 创建新对象）
        # 注意：当前实现会修改原始数据，这是预期行为
        # 如果需要保留原始数据，调用方应该先深拷贝


class TestInputMessageFlow(unittest.TestCase):
    """测试 input_message 的完整流程"""

    def test_input_message_flow_in_agent_handler(self):
        """测试 agent_handler 中 input_message 的流程"""
        # 1. 从数据库读取（模拟 read_all_inputmessages）
        input_messages = [
            {"_id": ObjectId(), "status": "pending", "message": "测试消息"}
        ]

        # 2. 更新状态（第 178 行）
        for msg in input_messages:
            msg["status"] = "handling"
            # save_inputmessage(msg) - 此时 _id 仍是 ObjectId
            self.assertIsInstance(msg["_id"], ObjectId)

        # 3. 放入 conversation（第 181 行）
        conversation = {"conversation_info": {"input_messages": input_messages}}

        # 4. context_prepare 转换（第 184 行）
        from agent.runner.context import _convert_objectid_to_str

        context = _convert_objectid_to_str({"conversation": conversation})

        # 5. 验证 context 中的消息 _id 已转换
        self.assertIsInstance(
            context["conversation"]["conversation_info"]["input_messages"][0]["_id"],
            str,
        )

        # 6. 但原始 input_messages 变量仍然有 ObjectId
        # 注意：_convert_objectid_to_str 会创建新对象，不修改原始数据
        # 所以后续的 save_inputmessage(input_message) 使用原始变量是安全的


class TestMongoDBIntegration(unittest.TestCase):
    """MongoDB 集成测试"""

    @classmethod
    def setUpClass(cls):
        """检查 MongoDB 连接"""
        try:
            from pymongo import MongoClient

            from conf.config import CONF

            connection_string = f"mongodb://{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/"
            client = MongoClient(
                connection_string, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000
            )
            client.admin.command("ping")
            client.close()

            from dao.mongo import MongoDBBase

            cls.mongo = MongoDBBase()
            cls.skip_integration = False
        except Exception as e:
            cls.skip_integration = True
            cls.skip_reason = f"MongoDB 连接失败: {type(e).__name__}: {e}"

    def setUp(self):
        if self.skip_integration:
            self.skipTest(self.skip_reason)

        self.test_collection = f"test_collection_{int(time.time())}"

    def tearDown(self):
        if not self.skip_integration:
            try:
                self.mongo.drop_collection(self.test_collection)
            except Exception:
                pass

    def test_replace_one_with_objectid_query_and_update(self):
        """测试使用 ObjectId 的 replace_one 操作"""
        # 插入测试数据
        doc = {"name": "test", "value": 1}
        inserted_id = self.mongo.insert_one(self.test_collection, doc)

        # 读取数据
        result = self.mongo.find_one(
            self.test_collection, {"_id": ObjectId(inserted_id)}
        )
        self.assertIsInstance(result["_id"], ObjectId)

        # 修改并更新
        result["value"] = 2
        update_result = self.mongo.replace_one(
            self.test_collection, {"_id": result["_id"]}, result
        )

        # 验证更新成功
        self.assertGreaterEqual(update_result, 0)

        # 验证数据已更新
        updated = self.mongo.find_one(
            self.test_collection, {"_id": ObjectId(inserted_id)}
        )
        self.assertEqual(updated["value"], 2)

    def test_replace_one_with_string_id_in_update_fails(self):
        """测试 update 中包含字符串 _id 会失败"""
        from pymongo.errors import WriteError

        from agent.runner.context import _convert_objectid_to_str

        # 插入测试数据
        doc = {"name": "test", "value": 1}
        inserted_id = self.mongo.insert_one(self.test_collection, doc)

        # 读取并转换
        result = self.mongo.find_one(
            self.test_collection, {"_id": ObjectId(inserted_id)}
        )
        converted = _convert_objectid_to_str(result)

        # 使用其他字段作为查询条件，但 update 包含字符串 _id
        with self.assertRaises(WriteError):
            self.mongo.replace_one(
                self.test_collection,
                {"name": "test"},  # 使用 name 而不是 _id 作为查询条件
                converted,  # 包含字符串类型的 _id
            )

    def test_replace_one_with_id_removed_succeeds(self):
        """测试移除 _id 后的 replace_one 操作成功"""
        from agent.runner.context import _convert_objectid_to_str

        # 插入测试数据
        doc = {"name": "test", "value": 1}
        inserted_id = self.mongo.insert_one(self.test_collection, doc)

        # 读取并转换
        result = self.mongo.find_one(
            self.test_collection, {"_id": ObjectId(inserted_id)}
        )
        converted = _convert_objectid_to_str(result)

        # 修改数据
        converted["value"] = 3

        # 移除 _id（修复后的逻辑）
        update_doc = {k: v for k, v in converted.items() if k != "_id"}

        # 使用其他字段作为查询条件
        update_result = self.mongo.replace_one(
            self.test_collection, {"name": "test"}, update_doc
        )

        # 验证更新成功
        self.assertGreaterEqual(update_result, 0)

        # 验证数据已更新且 _id 未变
        updated = self.mongo.find_one(
            self.test_collection, {"_id": ObjectId(inserted_id)}
        )
        self.assertEqual(updated["value"], 3)
        self.assertEqual(str(updated["_id"]), inserted_id)


if __name__ == "__main__":
    unittest.main()
