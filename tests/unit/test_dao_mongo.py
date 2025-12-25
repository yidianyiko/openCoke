# -*- coding: utf-8 -*-
"""
dao/mongo.py 单元测试 (使用 Mock)
"""
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestMongoDBBase:
    """测试 MongoDB 基础类"""

    @patch("dao.mongo.MongoClient")
    def test_init(self, mock_client):
        """测试初始化"""
        from dao.mongo import MongoDBBase

        db = MongoDBBase()
        assert db is not None
        mock_client.assert_called_once()

    @patch("dao.mongo.MongoClient")
    def test_get_collection(self, mock_client):
        """测试获取集合"""
        from dao.mongo import MongoDBBase

        mock_db = MagicMock()
        mock_client.return_value.__getitem__.return_value = mock_db

        db = MongoDBBase()
        collection = db.get_collection("test_collection")

        mock_db.__getitem__.assert_called_with("test_collection")

    @patch("dao.mongo.MongoClient")
    def test_insert_one(self, mock_client):
        """测试插入单个文档"""
        from dao.mongo import MongoDBBase

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        test_id = ObjectId()
        mock_result.inserted_id = test_id

        mock_client.return_value.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.insert_one.return_value = mock_result

        db = MongoDBBase()
        result = db.insert_one("test_collection", {"name": "test"})

        assert result == str(test_id)
        mock_collection.insert_one.assert_called_once()

    @patch("dao.mongo.MongoClient")
    def test_find_one(self, mock_client):
        """测试查找单个文档"""
        from dao.mongo import MongoDBBase

        mock_db = MagicMock()
        mock_collection = MagicMock()
        test_doc = {"_id": ObjectId(), "name": "test"}

        mock_client.return_value.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.find_one.return_value = test_doc

        db = MongoDBBase()
        result = db.find_one("test_collection", {"name": "test"})

        assert result == test_doc
        mock_collection.find_one.assert_called_once_with({"name": "test"})

    @patch("dao.mongo.MongoClient")
    def test_update_one(self, mock_client):
        """测试更新单个文档"""
        from dao.mongo import MongoDBBase

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.modified_count = 1

        mock_client.return_value.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.update_one.return_value = mock_result

        db = MongoDBBase()
        result = db.update_one(
            "test_collection", {"name": "test"}, {"$set": {"value": 100}}
        )

        assert result == 1
        mock_collection.update_one.assert_called_once()

    @patch("dao.mongo.MongoClient")
    def test_delete_one(self, mock_client):
        """测试删除单个文档"""
        from dao.mongo import MongoDBBase

        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 1

        mock_client.return_value.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.delete_one.return_value = mock_result

        db = MongoDBBase()
        result = db.delete_one("test_collection", {"name": "test"})

        assert result == 1
        mock_collection.delete_one.assert_called_once()


class TestVectorUtils:
    """测试向量工具类"""

    def test_cosine_similarity(self):
        """测试余弦相似度"""
        from dao.mongo import VectorUtils

        vec_a = [1.0, 0.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]
        similarity = VectorUtils.cosine_similarity(vec_a, vec_b)
        assert abs(similarity-1.0) < 0.001

        vec_c = [1.0, 0.0, 0.0]
        vec_d = [0.0, 1.0, 0.0]
        similarity = VectorUtils.cosine_similarity(vec_c, vec_d)
        assert abs(similarity-0.0) < 0.001

    def test_euclidean_distance(self):
        """测试欧氏距离"""
        from dao.mongo import VectorUtils

        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 1.0, 1.0]
        distance = VectorUtils.euclidean_distance(vec_a, vec_b)
        assert abs(distance-1.732) < 0.01

    def test_normalize_vector(self):
        """测试向量归一化"""
        from dao.mongo import VectorUtils

        vec = [3.0, 4.0]
        normalized = VectorUtils.normalize_vector(vec)
        # 归一化后长度应该为 1
        import numpy as np

        assert abs(np.linalg.norm(normalized)-1.0) < 0.001

    def test_average_vectors(self):
        """测试向量平均"""
        from dao.mongo import VectorUtils

        vectors = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
        avg = VectorUtils.average_vectors(vectors)
        assert abs(avg[0]-3.0) < 0.001
        assert abs(avg[1]-4.0) < 0.001

    def test_dot_product(self):
        """测试点积"""
        from dao.mongo import VectorUtils

        vec_a = [1.0, 2.0, 3.0]
        vec_b = [4.0, 5.0, 6.0]
        dot = VectorUtils.dot_product(vec_a, vec_b)
        # 1*4 + 2*5 + 3*6 = 32
        assert abs(dot-32.0) < 0.001
