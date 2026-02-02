# -*- coding: utf-8 -*-
"""
Pytest 配置文件

提供共享的 fixtures 和测试配置
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============ MongoDB Fixtures ============


@pytest.fixture(scope="session")
def mongodb_available():
    """检查 MongoDB 是否可用"""
    try:
        from pymongo import MongoClient

        from conf.config import CONF

        connection_string = f"mongodb://{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/"
        client = MongoClient(
            connection_string, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000
        )
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture
def mongo_client(mongodb_available):
    """提供 MongoDB 客户端，不可用时跳过测试"""
    if not mongodb_available:
        pytest.skip("MongoDB 不可用")

    from dao.mongo import MongoDBBase

    client = MongoDBBase()
    yield client
    client.close()


@pytest.fixture
def test_collection(mongo_client):
    """提供临时测试集合，测试后自动清理"""
    import time

    collection_name = f"test_collection_{int(time.time() * 1000)}"
    yield collection_name
    try:
        mongo_client.drop_collection(collection_name)
    except Exception:
        pass


# ============ Context Fixtures ============


@pytest.fixture
def sample_context():
    """提供标准的测试 context 结构"""
    from bson import ObjectId

    return {
        "user": {
            "_id": ObjectId(),
            "platforms": {"wechat": {"id": "wxid_test_user", "nickname": "测试用户"}},
        },
        "character": {
            "_id": ObjectId(),
            "platforms": {"wechat": {"id": "wxid_test_char", "nickname": "测试角色"}},
            "user_info": {
                "description": "测试角色描述",
                "status": {"place": "家里", "action": "休息"},
            },
        },
        "conversation": {
            "_id": ObjectId(),
            "conversation_info": {
                "chat_history": [],
                "input_messages": [],
                "input_messages_str": "",
                "chat_history_str": "",
                "time_str": "2024年12月25日",
                "photo_history": [],
                "future": {"timestamp": None, "action": None},
                "turn_sent_contents": [],
            },
        },
        "relation": {
            "_id": ObjectId(),
            "uid": "test_uid",
            "cid": "test_cid",
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


# ============ Reminder Fixtures ============


@pytest.fixture
def sample_reminder():
    """提供标准的测试提醒数据"""
    import time
    import uuid

    return {
        "reminder_id": str(uuid.uuid4()),
        "user_id": "test_user",
        "character_id": "test_char",
        "conversation_id": "test_conv",
        "title": "测试提醒",
        "next_trigger_time": int(time.time()) + 3600,
        "time_original": "1小时后",
        "timezone": "Asia/Shanghai",
        "recurrence": {"enabled": False},
        "status": "active",
    }


# ============ Markers ============


def pytest_configure(config):
    """注册自定义 markers"""
    config.addinivalue_line("markers", "integration: 需要外部服务的集成测试")
    config.addinivalue_line("markers", "slow: 耗时较长的测试")
    config.addinivalue_line("markers", "unit: 纯单元测试")


def pytest_collection_modifyitems(config, items):
    """自动为测试添加 markers"""
    for item in items:
        # 包含 integration 的测试文件自动标记
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)

        # 包含 e2e 的测试文件自动标记为 slow
        if "e2e" in item.nodeid:
            item.add_marker(pytest.mark.slow)

        # pbt (property-based testing) 测试标记为 slow
        if "pbt" in item.nodeid:
            item.add_marker(pytest.mark.slow)


# ============ Mock Fixtures ============


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB 客户端"""
    with patch("dao.mongo.MongoDBBase") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_llm_client():
    """Mock LLM API 客户端"""
    with patch("openai.OpenAI") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_embedding_client():
    """Mock Embedding API 客户端"""
    with patch("util.embedding_util.get_embedding") as mock:
        mock.return_value = [0.1] * 1536
        yield mock


# ============ Fixture Data ============


@pytest.fixture
def sample_text_message():
    """标准文本消息"""
    from tests.fixtures.sample_messages import get_text_message

    return get_text_message()


@pytest.fixture
def sample_voice_message():
    """标准语音消息"""
    from tests.fixtures.sample_messages import get_voice_message

    return get_voice_message()


@pytest.fixture
def sample_full_context():
    """完整的测试 context"""
    from tests.fixtures.sample_contexts import get_full_context

    return get_full_context()


@pytest.fixture
def sample_minimal_context():
    """最小化测试 context"""
    from tests.fixtures.sample_contexts import get_minimal_context

    return get_minimal_context()


# ============ Temporary Directory Fixtures ============


@pytest.fixture
def temp_test_dir(tmp_path):
    """临时测试目录"""
    test_dir = tmp_path / "test_data"
    test_dir.mkdir()
    return test_dir


@pytest.fixture
def temp_test_file(temp_test_dir):
    """临时测试文件"""
    test_file = temp_test_dir / "test.txt"
    test_file.write_text("测试内容")
    return test_file
