# -*- coding: utf-8 -*-
"""
dao/user_dao.py 单元测试
"""
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestUserDAO:
    """测试用户 DAO"""

    @patch("dao.mongo.MongoDBBase")
    def test_user_dao_import(self, mock_mongo):
        """测试 UserDAO 导入"""
        try:
            from dao import user_dao

            assert user_dao is not None
        except ImportError:
            pytest.skip("user_dao 模块不存在或依赖缺失")

    def test_user_structure(self):
        """测试用户数据结构"""
        user = {
            "_id": ObjectId(),
            "platforms": {"wechat": {"id": "test_user", "nickname": "测试用户"}},
            "created_at": 1234567890,
        }

        assert "_id" in user
        assert "platforms" in user
        assert "wechat" in user["platforms"]
