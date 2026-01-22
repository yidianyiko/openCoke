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
