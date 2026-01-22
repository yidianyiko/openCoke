# -*- coding: utf-8 -*-
import pytest


@pytest.mark.integration
def test_list_id_defaults_to_inbox():
    """测试 list_id 默认值为 inbox"""
    from dao.reminder_dao import ReminderDAO
    import time

    dao = ReminderDAO()

    # 先清理可能存在的旧数据
    dao.collection.delete_many({"user_id": "test_user", "title": "test reminder"})

    # 创建提醒时不指定 list_id
    reminder_data = {
        "user_id": "test_user",
        "title": "test reminder",
        "next_trigger_time": int(time.time()) + 3600,
    }

    inserted_id = dao.create_reminder(reminder_data)

    # 验证创建成功
    assert inserted_id is not None

    # 获取创建的提醒
    reminder = dao.collection.find_one({"user_id": "test_user", "title": "test reminder"})

    # 验证 list_id 为 inbox
    assert reminder["list_id"] == "inbox"

    # 清理
    dao.collection.delete_one({"_id": reminder["_id"]})
    dao.close()


@pytest.mark.integration
def test_create_reminder_with_custom_list_id():
    """测试创建提醒时可以指定自定义 list_id"""
    from dao.reminder_dao import ReminderDAO
    import time

    dao = ReminderDAO()

    # 先清理可能存在的旧数据
    dao.collection.delete_many({"user_id": "test_user", "title": "test reminder with custom list"})

    reminder_data = {
        "user_id": "test_user",
        "title": "test reminder with custom list",
        "next_trigger_time": int(time.time()) + 3600,
        "list_id": "work"  # 自定义 list_id
    }

    inserted_id = dao.create_reminder(reminder_data)
    assert inserted_id is not None

    reminder = dao.collection.find_one({"user_id": "test_user", "title": "test reminder with custom list"})
    assert reminder["list_id"] == "work"

    # 清理
    dao.collection.delete_one({"_id": reminder["_id"]})
    dao.close()


@pytest.mark.integration
def test_create_reminder_without_trigger_time():
    """测试创建无触发时间的提醒"""
    from dao.reminder_dao import ReminderDAO

    dao = ReminderDAO()

    reminder_data = {
        "user_id": "test_user",
        "title": "buy milk",
        "next_trigger_time": None,  # 无触发时间
        "list_id": "inbox"
    }

    inserted_id = dao.create_reminder(reminder_data)
    assert inserted_id is not None

    reminder = dao.collection.find_one({"user_id": "test_user", "title": "buy milk"})
    assert reminder["next_trigger_time"] is None
    assert reminder["list_id"] == "inbox"

    # 清理
    dao.collection.delete_one({"_id": reminder["_id"]})
    dao.close()


@pytest.mark.integration
def test_find_reminders_by_user_includes_null_trigger_time():
    """测试查询用户提醒时包含无时间的任务"""
    from dao.reminder_dao import ReminderDAO
    import time

    dao = ReminderDAO()

    # 创建一个有时间的提醒
    reminder_with_time = {
        "user_id": "test_user_2",
        "title": "reminder with time",
        "next_trigger_time": int(time.time()) + 3600,
        "list_id": "inbox",
        "status": "active"
    }
    dao.create_reminder(reminder_with_time)

    # 创建一个无时间的提醒
    reminder_no_time = {
        "user_id": "test_user_2",
        "title": "reminder without time",
        "next_trigger_time": None,
        "list_id": "inbox",
        "status": "active"
    }
    dao.create_reminder(reminder_no_time)

    # 查询用户所有提醒
    reminders = dao.find_reminders_by_user("test_user_2", status="active")

    # 应该返回两个提醒
    assert len(reminders) == 2

    titles = [r["title"] for r in reminders]
    assert "reminder with time" in titles
    assert "reminder without time" in titles

    # 清理
    dao.collection.delete_many({"user_id": "test_user_2"})
    dao.close()

