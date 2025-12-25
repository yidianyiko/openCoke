# -*- coding: utf-8 -*-
"""
提醒工具关键字操作集成测试

测试 reminder_tools.py 中基于关键字的操作：
- _delete_reminder_by_keyword
- _update_reminder_by_keyword
- _batch_op_delete (keyword)
- _batch_op_update (keyword)

Requirements:
- 工具层只支持关键字操作
- 正确处理各种边界情况
- 正确保存结果到 session_state
"""

import logging
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from dao.reminder_dao import ReminderDAO

logger = logging.getLogger(__name__)


@pytest.fixture
def reminder_dao(mongo_client):
    """提供 ReminderDAO 实例"""
    dao = ReminderDAO()
    dao.create_indexes()
    yield dao
    dao.close()


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return f"test_user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_reminders(reminder_dao, test_user_id):
    """测试后清理提醒"""
    yield
    reminder_dao.delete_all_by_user(test_user_id)


@pytest.fixture
def mock_session_state(test_user_id):
    """模拟 session_state"""
    from bson import ObjectId

    return {
        "user": {"_id": ObjectId()},
        "character": {"_id": ObjectId()},
        "conversation": {"_id": ObjectId()},
        "input_timestamp": int(time.time()),
    }


def create_test_reminder(reminder_dao, user_id, title, hours_later=1):
    """辅助函数：创建测试提醒"""
    current_time = int(time.time())
    reminder_data = {
        "user_id": user_id,
        "reminder_id": str(uuid.uuid4()),
        "title": title,
        "action_template": f"记得{title}",
        "next_trigger_time": current_time + hours_later * 3600,
        "time_original": f"{hours_later}小时后",
        "timezone": "Asia/Shanghai",
        "recurrence": {"enabled": False},
        "status": "confirmed",
    }
    reminder_dao.create_reminder(reminder_data)
    return reminder_data["reminder_id"]


class TestDeleteByKeyword:
    """_delete_reminder_by_keyword 测试"""

    def test_delete_success(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试成功删除"""
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 设置 session state
        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _delete_reminder_by_keyword(reminder_dao, test_user_id, "泡衣服")

        assert result["ok"] is True
        assert result["deleted_count"] == 1
        assert "泡衣服" in result["message"]
        logger.info(f"✓ 删除成功: {result['message']}")

    def test_delete_no_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试删除不存在的关键字"""
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _delete_reminder_by_keyword(reminder_dao, test_user_id, "游泳")

        assert result["ok"] is False
        assert "没有找到" in result["error"]
        logger.info(f"✓ 无匹配测试成功: {result['error']}")

    def test_delete_empty_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试空关键字"""
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _delete_reminder_by_keyword(reminder_dao, test_user_id, "")

        assert result["ok"] is False
        assert "keyword" in result["error"].lower() or "关键字" in result["error"]
        logger.info(f"✓ 空关键字测试成功: {result['error']}")

    def test_delete_none_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试 None 关键字"""
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _delete_reminder_by_keyword(reminder_dao, test_user_id, None)

        assert result["ok"] is False
        logger.info(f"✓ None 关键字测试成功: {result['error']}")

    def test_delete_all_with_wildcard(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试通配符删除所有"""
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")
        create_test_reminder(reminder_dao, test_user_id, "喝水")

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _delete_reminder_by_keyword(reminder_dao, test_user_id, "*")

        assert result["ok"] is True
        assert result["deleted_count"] == 3
        logger.info(f"✓ 通配符删除成功: {result['deleted_count']} 个")

    def test_delete_no_user_id(self, reminder_dao, cleanup_reminders):
        """测试无用户 ID"""
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        set_reminder_session_state({})

        result = _delete_reminder_by_keyword(reminder_dao, "", "泡衣服")

        assert result["ok"] is False
        assert "用户" in result["error"]
        logger.info(f"✓ 无用户 ID 测试成功: {result['error']}")


class TestUpdateByKeyword:
    """_update_reminder_by_keyword 测试"""

    def test_update_time_success(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试成功更新时间"""
        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        set_reminder_session_state({"user": {"_id": test_user_id}})

        # 更新时间
        new_time = "2025年12月26日15时00分"
        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="开会",
            new_title=None,
            new_trigger_time=new_time,
        )

        assert result["ok"] is True
        assert result["updated_count"] == 1
        assert "开会" in result["message"]
        logger.info(f"✓ 更新时间成功: {result['message']}")

    def test_update_title_success(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试成功更新标题"""
        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="开会",
            new_title="重要会议",
            new_trigger_time=None,
        )

        assert result["ok"] is True
        assert result["updated_count"] == 1
        logger.info(f"✓ 更新标题成功: {result['message']}")

        # 验证更新
        reminders = reminder_dao.find_reminders_by_user(
            test_user_id, status_list=["confirmed", "pending"]
        )
        assert reminders[0]["title"] == "重要会议"

    def test_update_no_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试更新不存在的关键字"""
        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="游泳",
            new_title="新标题",
            new_trigger_time=None,
        )

        assert result["ok"] is False
        assert "没有找到" in result["error"]
        logger.info(f"✓ 无匹配测试成功: {result['error']}")

    def test_update_empty_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试空关键字"""
        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="",
            new_title="新标题",
            new_trigger_time=None,
        )

        assert result["ok"] is False
        assert "keyword" in result["error"].lower() or "关键字" in result["error"]
        logger.info(f"✓ 空关键字测试成功: {result['error']}")

    def test_update_no_fields(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试无更新字段"""
        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="开会",
            new_title=None,
            new_trigger_time=None,
        )

        assert result["ok"] is False
        assert "没有提供" in result["error"] or "new_title" in result["error"]
        logger.info(f"✓ 无更新字段测试成功: {result['error']}")

    def test_update_invalid_time(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试无效时间格式"""
        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        set_reminder_session_state({"user": {"_id": test_user_id}})

        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="开会",
            new_title=None,
            new_trigger_time="无效时间格式",
        )

        assert result["ok"] is False
        assert "解析" in result["error"] or "时间" in result["error"]
        logger.info(f"✓ 无效时间测试成功: {result['error']}")


class TestBatchOperations:
    """批量操作测试"""

    def test_batch_delete_by_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试批量删除（关键字）"""
        from agent.agno_agent.tools.reminder_tools import (
            _BatchOperationContext,
            _batch_op_delete,
        )

        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        ctx = _BatchOperationContext(
            reminder_dao=reminder_dao,
            user_id=test_user_id,
            conversation_id=None,
            character_id=None,
            base_timestamp=int(time.time()),
        )

        result = _batch_op_delete(ctx, {"keyword": "泡衣服"})

        assert result["ok"] is True
        assert result["status"] == "deleted"
        assert result["deleted_count"] == 1
        logger.info(f"✓ 批量删除成功: {result}")

    def test_batch_delete_no_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试批量删除无关键字"""
        from agent.agno_agent.tools.reminder_tools import (
            _BatchOperationContext,
            _batch_op_delete,
        )

        ctx = _BatchOperationContext(
            reminder_dao=reminder_dao,
            user_id=test_user_id,
            conversation_id=None,
            character_id=None,
            base_timestamp=int(time.time()),
        )

        result = _batch_op_delete(ctx, {})

        assert result["ok"] is False
        assert "keyword" in result["error"].lower()
        logger.info(f"✓ 批量删除无关键字测试成功: {result['error']}")

    def test_batch_update_by_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试批量更新（关键字）"""
        from agent.agno_agent.tools.reminder_tools import (
            _BatchOperationContext,
            _batch_op_update,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        ctx = _BatchOperationContext(
            reminder_dao=reminder_dao,
            user_id=test_user_id,
            conversation_id=None,
            character_id=None,
            base_timestamp=int(time.time()),
        )

        result = _batch_op_update(
            ctx, {"keyword": "开会", "new_trigger_time": "2025年12月26日15时00分"}
        )

        assert result["ok"] is True
        assert result["status"] == "updated"
        assert result["updated_count"] == 1
        logger.info(f"✓ 批量更新成功: {result}")

    def test_batch_update_no_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试批量更新无关键字"""
        from agent.agno_agent.tools.reminder_tools import (
            _BatchOperationContext,
            _batch_op_update,
        )

        ctx = _BatchOperationContext(
            reminder_dao=reminder_dao,
            user_id=test_user_id,
            conversation_id=None,
            character_id=None,
            base_timestamp=int(time.time()),
        )

        result = _batch_op_update(ctx, {"new_title": "新标题"})

        assert result["ok"] is False
        assert "keyword" in result["error"].lower()
        logger.info(f"✓ 批量更新无关键字测试成功: {result['error']}")

    def test_batch_update_no_fields(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试批量更新无更新字段"""
        from agent.agno_agent.tools.reminder_tools import (
            _BatchOperationContext,
            _batch_op_update,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        ctx = _BatchOperationContext(
            reminder_dao=reminder_dao,
            user_id=test_user_id,
            conversation_id=None,
            character_id=None,
            base_timestamp=int(time.time()),
        )

        result = _batch_op_update(ctx, {"keyword": "开会"})

        assert result["ok"] is False
        assert "new_title" in result["error"] or "new_trigger_time" in result["error"]
        logger.info(f"✓ 批量更新无字段测试成功: {result['error']}")


class TestReminderToolIntegration:
    """reminder_tool 集成测试-测试内部函数"""

    def test_tool_delete_action(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试 delete action（通过内部函数）"""
        from agent.agno_agent.tools.reminder_tools import (
            _delete_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "泡衣服")

        session_state = {"user": {"_id": test_user_id}}
        set_reminder_session_state(session_state)

        result = _delete_reminder_by_keyword(reminder_dao, test_user_id, "泡衣服")

        assert result["ok"] is True
        assert result["deleted_count"] == 1
        logger.info(f"✓ delete action 成功: {result}")

    def test_tool_update_action(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试 update action（通过内部函数）"""
        from agent.agno_agent.tools.reminder_tools import (
            _update_reminder_by_keyword,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "开会")

        session_state = {"user": {"_id": test_user_id}}
        set_reminder_session_state(session_state)

        result = _update_reminder_by_keyword(
            reminder_dao,
            test_user_id,
            keyword="开会",
            new_title="重要会议",
            new_trigger_time=None,
        )

        assert result["ok"] is True
        assert result["updated_count"] == 1
        logger.info(f"✓ update action 成功: {result}")

    def test_tool_batch_action(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试 batch action（通过内部函数）"""
        import json

        from agent.agno_agent.tools.reminder_tools import (
            _batch_operations,
            set_reminder_session_state,
        )

        create_test_reminder(reminder_dao, test_user_id, "游泳")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        session_state = {
            "user": {"_id": test_user_id},
            "character": {"_id": "test_char"},
            "conversation": {"_id": "test_conv"},
            "input_timestamp": int(time.time()),
        }
        set_reminder_session_state(session_state)

        operations = json.dumps(
            [
                {"action": "delete", "keyword": "游泳"},
                {"action": "update", "keyword": "开会", "new_title": "重要会议"},
            ]
        )

        result = _batch_operations(
            reminder_dao=reminder_dao,
            user_id=test_user_id,
            operations_json=operations,
            conversation_id=None,
            character_id=None,
            base_timestamp=int(time.time()),
        )

        assert result["ok"] is True
        assert result["summary"]["deleted"] == 1
        assert result["summary"]["updated"] == 1
        logger.info(f"✓ batch action 成功: {result['summary']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
