# -*- coding: utf-8 -*-
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============ Context Fixtures ============


@pytest.fixture
def sample_context():
    """提供标准的测试 context 结构"""
    from bson import ObjectId

    return {
        "user": {
            "_id": ObjectId(),
            "display_name": "测试用户",
            "nickname": "测试用户",
            "platforms": {"wechat": {"id": "wxid_test_user", "nickname": "测试用户"}},
        },
        "character": {
            "_id": ObjectId(),
            "name": "测试角色",
            "nickname": "测试角色",
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
