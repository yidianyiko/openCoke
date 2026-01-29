# -*- coding: utf-8 -*-
"""
提醒和未来消息功能数据库测试脚本

直接测试数据库层面的功能，不依赖 LLM

Usage:
    python scripts/test_reminder_future_db.py
"""
import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()

import time

from util.log_util import get_logger

logger = get_logger(__name__)

from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.reminder_dao import ReminderDAO
from dao.user_dao import UserDAO
from util.time_util import format_time_friendly, parse_relative_time

# 测试用户和角色 ID
from_user = "6916f48dd16895f164265eea"  # 不辣的皮皮
to_user = "6916d8f79c455f8b8d06ecec"  # Coke

mongo = MongoDBBase()
user_dao = UserDAO()
conversation_dao = ConversationDAO()
reminder_dao = ReminderDAO()


def test_reminder_creation():
    """测试提醒创建功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 1: 提醒创建功能")
    logger.info("=" * 60)

    # 获取会话信息
    user = user_dao.get_user_by_id(from_user)
    character = user_dao.get_user_by_id(to_user)

    conversation = conversation_dao.get_private_conversation(
        "wechat",
        user["platforms"]["wechat"]["id"],
        character["platforms"]["wechat"]["id"],
    )

    if not conversation:
        logger.error("找不到会话")
        return False

    conversation_id = str(conversation["_id"])

    # 测试相对时间解析
    test_times = [
        "5分钟后",
        "30分钟后",
        "1小时后",
        "明天",
        "后天",
    ]

    logger.info("\n--- 测试相对时间解析 ---")
    for time_str in test_times:
        timestamp = parse_relative_time(time_str)
        if timestamp:
            friendly = format_time_friendly(timestamp)
            logger.info(f"  '{time_str}' -> {timestamp} ({friendly})")
        else:
            logger.warning(f"  '{time_str}' -> 解析失败")

    # 创建测试提醒
    logger.info("\n--- 创建测试提醒 ---")
    test_reminder = {
        "conversation_id": conversation_id,
        "user_id": from_user,
        "character_id": to_user,
        "title": "测试提醒-喝水",
        "next_trigger_time": int(time.time()) + 300,  # 5分钟后
        "time_original": "5分钟后",
        "timezone": "Asia/Shanghai",
        "recurrence": {"enabled": False},
        "action_template": "亲爱的，该喝水啦！记得保持水分哦~",
        "requires_confirmation": False,
    }

    try:
        inserted_id = reminder_dao.create_reminder(test_reminder)
        logger.info(f"✓ 提醒创建成功: {inserted_id}")

        # 查询创建的提醒
        reminder = reminder_dao.get_reminder_by_id(test_reminder["reminder_id"])
        if reminder:
            logger.info(f"  标题: {reminder.get('title')}")
            logger.info(
                f"  触发时间: {format_time_friendly(reminder.get('next_trigger_time'))}"
            )
            logger.info(f"  状态: {reminder.get('status')}")

        return True
    except Exception as e:
        logger.error(f"✗ 提醒创建失败: {e}")
        return False


def test_reminder_trigger():
    """测试提醒触发功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: 提醒触发功能")
    logger.info("=" * 60)

    # 创建一个即将触发的提醒
    user = user_dao.get_user_by_id(from_user)
    character = user_dao.get_user_by_id(to_user)

    conversation = conversation_dao.get_private_conversation(
        "wechat",
        user["platforms"]["wechat"]["id"],
        character["platforms"]["wechat"]["id"],
    )

    if not conversation:
        logger.error("找不到会话")
        return False

    conversation_id = str(conversation["_id"])

    # 创建一个已经到期的提醒（用于测试触发）
    test_reminder = {
        "conversation_id": conversation_id,
        "user_id": from_user,
        "character_id": to_user,
        "title": "测试触发提醒",
        "next_trigger_time": int(time.time()) - 60,  # 1分钟前（已到期）
        "time_original": "测试",
        "timezone": "Asia/Shanghai",
        "recurrence": {"enabled": False},
        "action_template": "这是一个测试触发的提醒消息",
        "status": "confirmed",
    }

    try:
        reminder_dao.create_reminder(test_reminder)
        logger.info("✓ 创建测试提醒成功")

        # 查找待触发的提醒
        now = int(time.time())
        pending_reminders = reminder_dao.find_pending_reminders(now)
        logger.info(f"  找到 {len(pending_reminders)} 个待触发提醒")

        for r in pending_reminders:
            logger.info(f" -{r.get('title')}: {r.get('action_template')[:30]}...")

        return len(pending_reminders) > 0
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}")
        return False


def test_future_message_planning():
    """测试未来消息规划功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 3: 未来消息规划功能")
    logger.info("=" * 60)

    user = user_dao.get_user_by_id(from_user)
    character = user_dao.get_user_by_id(to_user)

    conversation = conversation_dao.get_private_conversation(
        "wechat",
        user["platforms"]["wechat"]["id"],
        character["platforms"]["wechat"]["id"],
    )

    if not conversation:
        logger.error("找不到会话")
        return False

    conversation_id = str(conversation["_id"])

    # 设置未来消息规划
    future_timestamp = int(time.time()) + 3600  # 1小时后
    future_action = "聊一聊之前谈论过的话题"

    logger.info("设置未来消息规划:")
    logger.info(f"  时间: {format_time_friendly(future_timestamp)}")
    logger.info(f"  行动: {future_action}")

    try:
        # 更新会话的 future 字段
        conversation["conversation_info"]["future"] = {
            "timestamp": future_timestamp,
            "action": future_action,
            "proactive_times": 0,
        }

        conversation_dao.update_conversation_info(
            conversation_id, conversation["conversation_info"]
        )

        # 验证更新
        updated_conv = conversation_dao.get_conversation_by_id(conversation_id)
        future = updated_conv.get("conversation_info", {}).get("future", {})

        if future.get("action") == future_action:
            logger.info("✓ 未来消息规划设置成功")
            logger.info(f"  timestamp: {future.get('timestamp')}")
            logger.info(f"  action: {future.get('action')}")
            logger.info(f"  proactive_times: {future.get('proactive_times')}")
            return True
        else:
            logger.error("✗ 未来消息规划设置失败")
            return False

    except Exception as e:
        logger.error(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_future_message_query():
    """测试未来消息查询功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 4: 未来消息查询功能")
    logger.info("=" * 60)

    now = int(time.time())

    # 查询有未来消息规划的会话
    conversations = conversation_dao.find_conversations(
        query={
            "conversation_info.future.action": {"$ne": None, "$exists": True},
            "conversation_info.future.timestamp": {
                "$lt": now + 7200,
                "$gt": now - 1800,
            },  # 2小时内
        }
    )

    logger.info(f"找到 {len(conversations)} 个有未来消息规划的会话")

    for conv in conversations:
        future = conv.get("conversation_info", {}).get("future", {})
        logger.info(f"  会话 {conv['_id']}:")
        logger.info(f"    action: {future.get('action')}")
        logger.info(
            f"    timestamp: {format_time_friendly(future.get('timestamp', 0))}"
        )

    return True


def cleanup_test_data():
    """清理测试数据"""
    logger.info("\n" + "=" * 60)
    logger.info("清理测试数据")
    logger.info("=" * 60)

    # 清理测试提醒
    reminders = reminder_dao.find_reminders_by_user(from_user)
    for r in reminders:
        if "测试" in r.get("title", ""):
            reminder_dao.delete_reminder(r["reminder_id"])
            logger.info(f"  删除提醒: {r.get('title')}")

    # 清理未来消息规划
    user = user_dao.get_user_by_id(from_user)
    character = user_dao.get_user_by_id(to_user)

    conversation = conversation_dao.get_private_conversation(
        "wechat",
        user["platforms"]["wechat"]["id"],
        character["platforms"]["wechat"]["id"],
    )

    if conversation:
        conversation["conversation_info"]["future"] = {
            "timestamp": None,
            "action": None,
            "proactive_times": 0,
        }
        conversation_dao.update_conversation_info(
            str(conversation["_id"]), conversation["conversation_info"]
        )
        logger.info("  清理未来消息规划")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="提醒和未来消息功能数据库测试")
    parser.add_argument("--cleanup", action="store_true", help="清理测试数据")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_test_data()
        return

    logger.info("=" * 60)
    logger.info("提醒和未来消息功能数据库测试")
    logger.info("=" * 60)

    results = []

    # 运行测试
    results.append(("提醒创建", test_reminder_creation()))
    results.append(("提醒触发", test_reminder_trigger()))
    results.append(("未来消息规划", test_future_message_planning()))
    results.append(("未来消息查询", test_future_message_query()))

    # 输出结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        logger.info(f"  {name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\n所有测试通过!")
    else:
        logger.info("\n部分测试失败，请检查日志")

    # 询问是否清理
    logger.info(
        "\n运行 'python scripts/test_reminder_future_db.py --cleanup' 清理测试数据"
    )


if __name__ == "__main__":
    main()
