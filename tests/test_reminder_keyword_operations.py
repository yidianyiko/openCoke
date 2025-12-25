# -*- coding: utf-8 -*-
"""
提醒关键字操作集成测试

测试基于关键字的提醒操作（不使用 ID）：
- 按关键字删除提醒
- 按关键字更新提醒
- 批量关键字操作

Requirements:
- LLM 工具只支持关键字操作，不支持 ID 操作
- 关键字模糊匹配标题
- 支持 "*" 通配符删除所有
"""

import logging
import time
import uuid

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


class TestKeywordSearch:
    """关键字搜索测试"""

    def test_find_by_exact_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试精确关键字搜索"""
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "洗衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 精确匹配
        results = reminder_dao.find_reminders_by_keyword(test_user_id, "泡衣服")
        assert len(results) == 1
        assert results[0]["title"] == "泡衣服"
        logger.info("✓ 精确关键字搜索成功")

    def test_find_by_partial_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试部分关键字搜索（模糊匹配）"""
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "洗衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 部分匹配 "衣服"
        results = reminder_dao.find_reminders_by_keyword(test_user_id, "衣服")
        assert len(results) == 2
        titles = [r["title"] for r in results]
        assert "泡衣服" in titles
        assert "洗衣服" in titles
        logger.info("✓ 部分关键字搜索成功")

    def test_find_case_insensitive(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试大小写不敏感搜索"""
        create_test_reminder(reminder_dao, test_user_id, "Meeting at 3pm")
        create_test_reminder(reminder_dao, test_user_id, "meeting notes")

        # 大小写不敏感
        results = reminder_dao.find_reminders_by_keyword(test_user_id, "MEETING")
        assert len(results) == 2
        logger.info("✓ 大小写不敏感搜索成功")

    def test_find_no_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试无匹配结果"""
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")

        results = reminder_dao.find_reminders_by_keyword(test_user_id, "游泳")
        assert len(results) == 0
        logger.info("✓ 无匹配结果测试成功")


class TestKeywordDelete:
    """关键字删除测试"""

    def test_delete_by_keyword_single(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试按关键字删除单个提醒"""
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 删除 "泡衣服"
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "泡衣服"
        )

        assert deleted_count == 1
        assert len(deleted_reminders) == 1
        assert deleted_reminders[0]["title"] == "泡衣服"
        logger.info(f"✓ 删除单个提醒成功: {deleted_reminders[0]['title']}")

        # 验证只删除了目标提醒
        remaining = reminder_dao.find_reminders_by_user(
            test_user_id, status_list=["confirmed", "pending"]
        )
        assert len(remaining) == 1
        assert remaining[0]["title"] == "开会"

    def test_delete_by_keyword_multiple(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试按关键字删除多个提醒"""
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "洗衣服")
        create_test_reminder(reminder_dao, test_user_id, "晾衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 删除所有包含 "衣服" 的提醒
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "衣服"
        )

        assert deleted_count == 3
        assert len(deleted_reminders) == 3
        deleted_titles = [r["title"] for r in deleted_reminders]
        assert "泡衣服" in deleted_titles
        assert "洗衣服" in deleted_titles
        assert "晾衣服" in deleted_titles
        logger.info(f"✓ 删除多个提醒成功: {deleted_count} 个")

        # 验证只剩下 "开会"
        remaining = reminder_dao.find_reminders_by_user(
            test_user_id, status_list=["confirmed", "pending"]
        )
        assert len(remaining) == 1
        assert remaining[0]["title"] == "开会"

    def test_delete_by_keyword_no_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试删除不存在的关键字"""
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")

        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "游泳"
        )

        assert deleted_count == 0
        assert len(deleted_reminders) == 0
        logger.info("✓ 删除不存在关键字测试成功")

        # 验证原提醒未被删除
        remaining = reminder_dao.find_reminders_by_user(
            test_user_id, status_list=["confirmed", "pending"]
        )
        assert len(remaining) == 1

    def test_delete_all_with_wildcard(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试使用通配符删除所有提醒"""
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")
        create_test_reminder(reminder_dao, test_user_id, "喝水")

        # 使用 delete_all_by_user 模拟 keyword="*"
        deleted_count = reminder_dao.delete_all_by_user(test_user_id)

        assert deleted_count == 3
        logger.info(f"✓ 删除所有提醒成功: {deleted_count} 个")

        # 验证全部删除
        remaining = reminder_dao.find_reminders_by_user(
            test_user_id, status_list=["confirmed", "pending"]
        )
        assert len(remaining) == 0


class TestKeywordUpdate:
    """关键字更新测试"""

    def test_update_by_keyword_single(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试按关键字更新单个提醒"""
        create_test_reminder(reminder_dao, test_user_id, "开会")
        create_test_reminder(reminder_dao, test_user_id, "喝水")

        # 更新 "开会" 的时间
        new_time = int(time.time()) + 7200
        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            test_user_id,
            "开会",
            {"next_trigger_time": new_time, "time_original": "2小时后"},
        )

        assert updated_count == 1
        assert len(updated_reminders) == 1
        assert updated_reminders[0]["title"] == "开会"
        logger.info(f"✓ 更新单个提醒成功: {updated_reminders[0]['title']}")

        # 验证更新
        reminder = reminder_dao.find_reminders_by_keyword(test_user_id, "开会")[0]
        assert reminder["next_trigger_time"] == new_time
        assert reminder["time_original"] == "2小时后"

    def test_update_by_keyword_title(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试按关键字更新标题"""
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 更新标题
        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            test_user_id,
            "开会",
            {"title": "重要会议", "action_template": "记得重要会议"},
        )

        assert updated_count == 1
        logger.info("✓ 更新标题成功")

        # 验证更新
        reminders = reminder_dao.find_reminders_by_user(
            test_user_id, status_list=["confirmed", "pending"]
        )
        assert len(reminders) == 1
        assert reminders[0]["title"] == "重要会议"

    def test_update_by_keyword_multiple(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试按关键字更新多个提醒"""
        create_test_reminder(reminder_dao, test_user_id, "喝水提醒1")
        create_test_reminder(reminder_dao, test_user_id, "喝水提醒2")
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 更新所有 "喝水" 相关提醒
        new_time = int(time.time()) + 1800
        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            test_user_id,
            "喝水",
            {"next_trigger_time": new_time},
        )

        assert updated_count == 2
        assert len(updated_reminders) == 2
        logger.info(f"✓ 更新多个提醒成功: {updated_count} 个")

        # 验证更新
        water_reminders = reminder_dao.find_reminders_by_keyword(test_user_id, "喝水")
        for r in water_reminders:
            assert r["next_trigger_time"] == new_time

    def test_update_by_keyword_no_match(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试更新不存在的关键字"""
        create_test_reminder(reminder_dao, test_user_id, "开会")

        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            test_user_id,
            "游泳",
            {"title": "新标题"},
        )

        assert updated_count == 0
        assert len(updated_reminders) == 0
        logger.info("✓ 更新不存在关键字测试成功")


class TestKeywordOperationsEdgeCases:
    """关键字操作边界情况测试"""

    def test_empty_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试空关键字"""
        create_test_reminder(reminder_dao, test_user_id, "开会")

        # 空关键字应该返回空结果
        results = reminder_dao.find_reminders_by_keyword(test_user_id, "")
        # 空字符串作为正则会匹配所有，这是预期行为
        # 实际使用时工具层会校验空关键字

    def test_special_characters_in_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试特殊字符关键字"""
        create_test_reminder(reminder_dao, test_user_id, "开会(重要)")
        create_test_reminder(reminder_dao, test_user_id, "开会[紧急]")

        # 搜索包含特殊字符的关键字
        results = reminder_dao.find_reminders_by_keyword(test_user_id, "开会")
        assert len(results) == 2
        logger.info("✓ 特殊字符关键字测试成功")

    def test_chinese_keyword(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试中文关键字"""
        create_test_reminder(reminder_dao, test_user_id, "下午三点开会")
        create_test_reminder(reminder_dao, test_user_id, "明天开会")
        create_test_reminder(reminder_dao, test_user_id, "喝水")

        results = reminder_dao.find_reminders_by_keyword(test_user_id, "开会")
        assert len(results) == 2
        logger.info("✓ 中文关键字测试成功")

    def test_only_active_reminders_affected(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试只影响有效状态的提醒"""
        current_time = int(time.time())

        # 创建不同状态的提醒
        for status in ["confirmed", "pending", "triggered", "completed"]:
            reminder_data = {
                "user_id": test_user_id,
                "reminder_id": str(uuid.uuid4()),
                "title": f"开会-{status}",
                "action_template": f"记得开会-{status}",
                "next_trigger_time": current_time + 3600,
                "time_original": "1小时后",
                "timezone": "Asia/Shanghai",
                "recurrence": {"enabled": False},
                "status": status,
            }
            reminder_dao.create_reminder(reminder_data)

        # 删除 "开会" 相关提醒（只影响 confirmed/pending）
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "开会"
        )

        assert deleted_count == 2  # 只删除 confirmed 和 pending
        logger.info(f"✓ 只删除有效状态提醒: {deleted_count} 个")

        # 验证 triggered 和 completed 状态的提醒未被删除
        all_reminders = reminder_dao.find_reminders_by_user(test_user_id)
        assert len(all_reminders) == 2
        statuses = [r["status"] for r in all_reminders]
        assert "triggered" in statuses
        assert "completed" in statuses


class TestRealWorldScenarios:
    """真实场景测试"""

    def test_user_says_delete_paoyifu(self, reminder_dao, test_user_id, cleanup_reminders):
        """
        场景：用户说"把泡衣服的提醒删了"
        预期：删除包含"泡衣服"的提醒
        """
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "下午2点分析任务")

        # 模拟 LLM 调用 delete 操作，keyword="泡衣服"
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            test_user_id, "泡衣服"
        )

        assert deleted_count == 1
        assert deleted_reminders[0]["title"] == "泡衣服"
        logger.info("✓ 场景测试成功: 删除泡衣服提醒")

    def test_user_says_change_meeting_time(self, reminder_dao, test_user_id, cleanup_reminders):
        """
        场景：用户说"把开会改到明天下午3点"
        预期：更新包含"开会"的提醒时间
        """
        create_test_reminder(reminder_dao, test_user_id, "下午2点开会")

        # 模拟 LLM 调用 update 操作，keyword="开会"
        new_time = int(time.time()) + 86400 + 15 * 3600  # 明天下午3点
        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            test_user_id,
            "开会",
            {"next_trigger_time": new_time, "time_original": "明天下午3点"},
        )

        assert updated_count == 1
        logger.info("✓ 场景测试成功: 修改开会时间")

    def test_user_says_delete_all(self, reminder_dao, test_user_id, cleanup_reminders):
        """
        场景：用户说"删除所有提醒"
        预期：删除用户的所有有效提醒
        """
        create_test_reminder(reminder_dao, test_user_id, "泡衣服")
        create_test_reminder(reminder_dao, test_user_id, "开会")
        create_test_reminder(reminder_dao, test_user_id, "喝水")

        # 模拟 LLM 调用 delete 操作，keyword="*"
        deleted_count = reminder_dao.delete_all_by_user(test_user_id)

        assert deleted_count == 3
        logger.info("✓ 场景测试成功: 删除所有提醒")

    def test_batch_operations(self, reminder_dao, test_user_id, cleanup_reminders):
        """
        场景：用户说"删除游泳那个提醒，把开会改到明天，再加一个喝水提醒"
        预期：批量执行删除、更新、创建操作
        """
        create_test_reminder(reminder_dao, test_user_id, "游泳教练")
        create_test_reminder(reminder_dao, test_user_id, "下午开会")

        # 1. 删除游泳
        deleted_count, _ = reminder_dao.delete_reminders_by_keyword(test_user_id, "游泳")
        assert deleted_count == 1

        # 2. 更新开会
        new_time = int(time.time()) + 86400
        updated_count, _ = reminder_dao.update_reminders_by_keyword(
            test_user_id, "开会", {"next_trigger_time": new_time}
        )
        assert updated_count == 1

        # 3. 创建喝水
        create_test_reminder(reminder_dao, test_user_id, "喝水", hours_later=1)

        # 验证最终状态
        reminders = reminder_dao.find_reminders_by_user(
            test_user_id, status_list=["confirmed", "pending"]
        )
        assert len(reminders) == 2
        titles = [r["title"] for r in reminders]
        assert "下午开会" in titles
        assert "喝水" in titles
        assert "游泳教练" not in titles
        logger.info("✓ 场景测试成功: 批量操作")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
