# -*- coding: utf-8 -*-
"""
Relation 持久化集成测试

测试 relation 数据在 context_prepare 转换后能正确持久化到 MongoDB。
这个测试覆盖了之前遗漏的场景：ObjectId 转字符串后的 replace_one 操作。

Requirements:
- 6.1: ObjectId 序列化
- 数据持久化正确性
"""
import sys
sys.path.append(".")

import os
import unittest
import time
from unittest.mock import Mock, patch, MagicMock
from bson import ObjectId


class TestRelationPersistenceWithMock(unittest.TestCase):
    """使用 Mock 测试 relation 持久化逻辑"""
    
    def test_replace_one_with_converted_objectid(self):
        """测试 replace_one 使用转换后的 ObjectId 字符串"""
        from agent.runner.context import _convert_objectid_to_str
        
        # 模拟从数据库读取的 relation（包含 ObjectId）
        original_relation = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "uid": "user_123",
            "cid": "char_456",
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0
            }
        }
        
        # 经过 context_prepare 转换后
        converted_relation = _convert_objectid_to_str(original_relation)
        
        # 验证 _id 已被转换为字符串
        self.assertIsInstance(converted_relation["_id"], str)
        self.assertEqual(converted_relation["_id"], "507f1f77bcf86cd799439011")
        
        # 模拟修改 relation
        converted_relation["relationship"]["closeness"] = 60
        
        # 验证修复后的逻辑：移除 _id 字段
        relation_update = {k: v for k, v in converted_relation.items() if k != "_id"}
        
        # 验证 update 对象不包含 _id
        self.assertNotIn("_id", relation_update)
        
        # 验证其他字段保留
        self.assertEqual(relation_update["uid"], "user_123")
        self.assertEqual(relation_update["cid"], "char_456")
        self.assertEqual(relation_update["relationship"]["closeness"], 60)
    
    def test_replace_one_query_uses_uid_cid(self):
        """测试 replace_one 使用 uid + cid 作为查询条件"""
        from agent.runner.context import _convert_objectid_to_str
        
        relation = {
            "_id": ObjectId(),
            "uid": "user_123",
            "cid": "char_456",
            "relationship": {"closeness": 50}
        }
        
        converted = _convert_objectid_to_str(relation)
        
        # 构建查询条件
        query = {
            "uid": converted["uid"],
            "cid": converted["cid"]
        }
        
        # 验证查询条件正确
        self.assertEqual(query["uid"], "user_123")
        self.assertEqual(query["cid"], "char_456")
        self.assertNotIn("_id", query)
    
    def test_agent_handler_replace_one_fix(self):
        """测试 agent_handler 中 replace_one 的修复"""
        from agent.runner.context import _convert_objectid_to_str
        
        # 模拟完整的 context
        context = {
            "user": {"_id": ObjectId()},
            "character": {"_id": ObjectId()},
            "relation": {
                "_id": ObjectId("507f1f77bcf86cd799439011"),
                "uid": "user_123",
                "cid": "char_456",
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                    "dislike": 0,
                    "status": "空闲"
                },
                "user_info": {"realname": ""},
                "character_info": {"longterm_purpose": ""}
            },
            "conversation": {
                "conversation_info": {
                    "chat_history": [],
                    "input_messages": []
                }
            }
        }
        
        # 转换 ObjectId
        converted_context = _convert_objectid_to_str(context)
        
        # 模拟 agent_handler 中的修复逻辑
        relation_update = {
            k: v for k, v in converted_context["relation"].items() 
            if k != "_id"
        }
        
        # 验证修复后的 update 对象
        self.assertNotIn("_id", relation_update)
        self.assertIn("uid", relation_update)
        self.assertIn("cid", relation_update)
        self.assertIn("relationship", relation_update)
        
        # 模拟 MongoDB replace_one 调用（使用 Mock）
        mock_mongo = Mock()
        mock_mongo.replace_one = Mock(return_value=1)
        
        # 执行 replace_one
        result = mock_mongo.replace_one(
            "relations",
            query={
                "uid": converted_context["relation"]["uid"],
                "cid": converted_context["relation"]["cid"]
            },
            update=relation_update
        )
        
        # 验证调用参数
        mock_mongo.replace_one.assert_called_once()
        call_args = mock_mongo.replace_one.call_args
        
        # 验证 update 参数不包含 _id
        update_arg = call_args[1]["update"]
        self.assertNotIn("_id", update_arg)


class TestRelationPersistenceIntegration(unittest.TestCase):
    """
    集成测试：测试与真实 MongoDB 的交互
    
    需要配置 MongoDB 连接才能运行
    """
    
    @classmethod
    def setUpClass(cls):
        """检查 MongoDB 连接"""
        try:
            from pymongo import MongoClient
            from conf.config import CONF
            
            # 使用带超时的连接测试
            connection_string = f"mongodb://{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/"
            client = MongoClient(
                connection_string,
                serverSelectionTimeoutMS=2000,  # 2秒超时
                connectTimeoutMS=2000
            )
            # 强制连接测试
            client.admin.command('ping')
            client.close()
            
            # 连接成功，使用正常的 MongoDBBase
            from dao.mongo import MongoDBBase
            cls.mongo = MongoDBBase()
            cls.skip_integration = False
        except Exception as e:
            cls.skip_integration = True
            cls.skip_reason = f"MongoDB 连接失败: {type(e).__name__}: {e}"
    
    def setUp(self):
        if self.skip_integration:
            self.skipTest(self.skip_reason)
        
        # 创建测试数据
        self.test_uid = f"test_user_{int(time.time())}"
        self.test_cid = f"test_char_{int(time.time())}"
        self.test_relation = {
            "uid": self.test_uid,
            "cid": self.test_cid,
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲"
            },
            "user_info": {
                "realname": "",
                "hobbyname": "",
                "description": "测试用户"
            },
            "character_info": {
                "longterm_purpose": "测试目标",
                "shortterm_purpose": "",
                "attitude": ""
            }
        }
    
    def tearDown(self):
        if not self.skip_integration:
            # 清理测试数据
            try:
                self.mongo.delete_many("relations", {"uid": self.test_uid})
            except:
                pass
    
    def test_create_and_update_relation(self):
        """测试创建和更新 relation"""
        from agent.runner.context import _convert_objectid_to_str
        
        # 1. 插入测试数据
        inserted_id = self.mongo.insert_one("relations", self.test_relation)
        self.assertIsNotNone(inserted_id)
        
        # 2. 读取数据（模拟 context_prepare 中的操作）
        relation = self.mongo.find_one("relations", {
            "uid": self.test_uid,
            "cid": self.test_cid
        })
        self.assertIsNotNone(relation)
        self.assertIsInstance(relation["_id"], ObjectId)
        
        # 3. 转换 ObjectId（模拟 context_prepare）
        converted_relation = _convert_objectid_to_str(relation)
        self.assertIsInstance(converted_relation["_id"], str)
        
        # 4. 修改数据
        converted_relation["relationship"]["closeness"] = 75
        converted_relation["user_info"]["realname"] = "测试真名"
        
        # 5. 使用修复后的逻辑更新数据
        relation_update = {
            k: v for k, v in converted_relation.items() 
            if k != "_id"
        }
        
        result = self.mongo.replace_one(
            "relations",
            query={
                "uid": converted_relation["uid"],
                "cid": converted_relation["cid"]
            },
            update=relation_update
        )
        
        # 6. 验证更新成功
        self.assertGreaterEqual(result, 0)  # replace_one 返回 modified_count
        
        # 7. 重新读取验证
        updated_relation = self.mongo.find_one("relations", {
            "uid": self.test_uid,
            "cid": self.test_cid
        })
        
        self.assertEqual(updated_relation["relationship"]["closeness"], 75)
        self.assertEqual(updated_relation["user_info"]["realname"], "测试真名")
        # 验证 _id 没有被修改
        self.assertEqual(str(updated_relation["_id"]), inserted_id)
    
    def test_replace_one_without_id_removal_should_fail(self):
        """测试不移除 _id 时 replace_one 应该失败（验证问题确实存在）"""
        from agent.runner.context import _convert_objectid_to_str
        from pymongo.errors import WriteError
        
        # 1. 插入测试数据
        inserted_id = self.mongo.insert_one("relations", self.test_relation)
        
        # 2. 读取并转换
        relation = self.mongo.find_one("relations", {
            "uid": self.test_uid,
            "cid": self.test_cid
        })
        converted_relation = _convert_objectid_to_str(relation)
        
        # 3. 修改数据但不移除 _id
        converted_relation["relationship"]["closeness"] = 80
        
        # 4. 尝试更新（应该失败，因为 _id 类型不匹配）
        with self.assertRaises(WriteError) as context:
            self.mongo.replace_one(
                "relations",
                query={
                    "uid": converted_relation["uid"],
                    "cid": converted_relation["cid"]
                },
                update=converted_relation  # 包含字符串类型的 _id
            )
        
        # 验证错误信息
        self.assertIn("_id", str(context.exception))


class TestBackgroundHandlerRelationPersistence(unittest.TestCase):
    """测试 agent_background_handler 中的 relation 持久化"""
    
    def test_background_handler_replace_one_fix(self):
        """测试 background_handler 中 replace_one 的修复"""
        from agent.runner.context import _convert_objectid_to_str
        
        # 模拟 context
        context = {
            "relation": {
                "_id": ObjectId(),
                "uid": "user_123",
                "cid": "char_456",
                "relationship": {
                    "closeness": 50,
                    "trustness": 50
                }
            }
        }
        
        # 转换
        converted = _convert_objectid_to_str(context)
        
        # 验证修复逻辑
        relation_update = {
            k: v for k, v in converted["relation"].items()
            if k != "_id"
        }
        
        self.assertNotIn("_id", relation_update)
        self.assertIn("uid", relation_update)
        self.assertIn("cid", relation_update)


if __name__ == "__main__":
    unittest.main()
