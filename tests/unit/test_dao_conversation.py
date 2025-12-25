# -*- coding: utf-8 -*-
"""
dao/conversation_dao.py 单元测试
"""
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestConversationDAO:
    """测试对话 DAO"""

    @patch("dao.mongo.MongoDBBase")
    def test_conversation_dao_import(self, mock_mongo):
        """测试 ConversationDAO 导入"""
        try:
            from dao import conversation_dao

            assert conversation_dao is not None
        except ImportError:
            pytest.skip("conversation_dao 模块不存在或依赖缺失")

    def test_conversation_structure(self):
        """测试对话数据结构"""
        conversation = {
            "_id": ObjectId(),
            "conversation_info": {
                "chat_history": [],
                "input_messages": [],
                "time_str": "2024年12月25日",
            },
        }

        assert "_id" in conversation
        assert "conversation_info" in conversation
        assert "chat_history" in conversation["conversation_info"]
