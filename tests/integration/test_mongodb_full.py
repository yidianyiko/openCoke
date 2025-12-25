# -*- coding: utf-8 -*-
"""
MongoDB 完整集成测试
"""
import pytest


@pytest.mark.integration
class TestMongoDBIntegration:
    """MongoDB 集成测试"""

    def test_connection(self, mongo_client):
        """测试 MongoDB 连接"""
        assert mongo_client is not None

    def test_insert_and_find(self, mongo_client, test_collection):
        """测试插入和查询"""
        # 插入文档
        doc = {"name": "test", "value": 123}
        doc_id = mongo_client.insert_one(test_collection, doc)
        assert doc_id is not None

        # 查询文档
        from bson import ObjectId

        found = mongo_client.find_one(test_collection, {"_id": ObjectId(doc_id)})
        assert found is not None
        assert found["name"] == "test"
        assert found["value"] == 123

    def test_update(self, mongo_client, test_collection):
        """测试更新"""
        # 插入文档
        doc = {"name": "test", "value": 100}
        doc_id = mongo_client.insert_one(test_collection, doc)

        # 更新文档
        from bson import ObjectId

        result = mongo_client.update_one(
            test_collection, {"_id": ObjectId(doc_id)}, {"$set": {"value": 200}}
        )
        assert result == 1

        # 验证更新
        found = mongo_client.find_one(test_collection, {"_id": ObjectId(doc_id)})
        assert found["value"] == 200

    def test_delete(self, mongo_client, test_collection):
        """测试删除"""
        # 插入文档
        doc = {"name": "test", "value": 123}
        doc_id = mongo_client.insert_one(test_collection, doc)

        # 删除文档
        from bson import ObjectId

        result = mongo_client.delete_one(test_collection, {"_id": ObjectId(doc_id)})
        assert result == 1

        # 验证删除
        found = mongo_client.find_one(test_collection, {"_id": ObjectId(doc_id)})
        assert found is None

    def test_count(self, mongo_client, test_collection):
        """测试计数"""
        # 插入多个文档
        docs = [{"name": f"test_{i}", "value": i} for i in range(5)]
        mongo_client.insert_many(test_collection, docs)

        # 计数
        count = mongo_client.count_documents(test_collection)
        assert count == 5

    def test_find_many(self, mongo_client, test_collection):
        """测试批量查询"""
        # 插入多个文档
        docs = [{"name": f"test_{i}", "value": i} for i in range(10)]
        mongo_client.insert_many(test_collection, docs)

        # 查询
        results = mongo_client.find_many(test_collection, {}, limit=5)
        assert len(results) == 5
