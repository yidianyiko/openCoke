# -*- coding: utf-8 -*-
"""
用户对话功能测试脚本

测试内容：
1. 用户对话是否可以触发未来消息
2. 用户对话是否可以触发消息提醒功能

Usage:
    python scripts/test_dialog_features.py
"""
import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()
import asyncio
import time

from util.log_util import get_logger

logger = get_logger(__name__)

from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.reminder_dao import ReminderDAO
from dao.user_dao import UserDAO

# 测试用户和角色 ID
from_user = "6916f48dd16895f164265eea"  # 不辣的皮皮
to_user = "6916d8f79c455f8b8d06ecec"  # Coke

mongo = MongoDBBase()
user_dao = UserDAO()
conversation_dao = ConversationDAO()
reminder_dao = ReminderDAO()


def send_test_message(message_text: str):
    """发送测试消息到 inputmessages"""
    now = int(time.time())
    message = {
        "input_timestamp": now,
        "handled_timestamp": now,
        "status": "pending",
        "from_user": from_user,
        "platform": "wechat",
        "chatroom_name": None,
        "to_user": to_user,
        "message_type": "text",
        "message": message_text,
        "metadata": {},
    }
    msg_id = mongo.insert_one("inputmessages", message)
    logger.info(f"发送消息: {message_text} (ID: {msg_id})")
    return msg_id


def check_output_messages():
    """检查输出消息"""
    now = int(time.time())
    messages = mongo.find_many(
        "outputmessages",
        {
            "platform": "wechat",
            "from_user": to_user,
            "to_user": from_user,
        },
        limit=10,
    )

    logger.info(f"=== 输出消息 ({len(messages)} 条) ===")
    for msg in messages:
        logger.info(
            f"  [{msg.get('status')}] {msg.get('message_type')}: {msg.get('message', '')[:50]}..."
        )
    return messages


def check_reminders():
    """检查提醒列表"""
    reminders = reminder_dao.find_reminders_by_user(from_user)
    logger.info(f"=== 提醒列表 ({len(reminders)} 条) ===")
    for r in reminders:
        logger.info(
            f"  [{r.get('status')}] {r.get('title')}-触发时间: {r.get('next_trigger_time')}"
        )
    return reminders


def check_future_messages():
    """检查未来消息规划"""
    user = user_dao.get_user_by_id(from_user)
    character = user_dao.get_user_by_id(to_user)

    conversation = conversation_dao.get_private_conversation(
        "wechat",
        user["platforms"]["wechat"]["id"],
        character["platforms"]["wechat"]["id"],
    )

    if conversation:
        future = conversation.get("conversation_info", {}).get("future", {})
        logger.info("=== 未来消息规划 ===")
        logger.info(f"  timestamp: {future.get('timestamp')}")
        logger.info(f"  action: {future.get('action')}")
        logger.info(f"  proactive_times: {future.get('proactive_times')}")
        return future
    return None


async def run_handler_once():
    """运行一次 handler"""
    from agent.runner.agent_handler import handler

    logger.info("运行 handler...")
    await handler()
    logger.info("handler 执行完成")


async def run_background_handler_once():
    """运行一次 background handler"""
    from agent.runner.agent_background_handler import background_handler

    logger.info("运行 background_handler...")
    await background_handler()
    logger.info("background_handler 执行完成")


def clear_test_data():
    """清理测试数据"""
    # 清理 pending 的输入消息
    mongo.delete_many("inputmessages", {"from_user": from_user, "status": "pending"})
    logger.info("已清理 pending 输入消息")


async def test_reminder_trigger():
    """测试提醒触发功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 1: 提醒触发功能")
    logger.info("=" * 60)

    # 发送包含提醒意图的消息
    test_messages = [
        "帮我设置一个5分钟后的提醒，提醒我喝水",
        "明天早上8点提醒我开会",
        "30分钟后提醒我休息一下",
    ]

    for msg in test_messages[:1]:  # 只测试第一条
        logger.info(f"\n发送测试消息: {msg}")
        send_test_message(msg)

        # 等待一下让消息入库
        await asyncio.sleep(1)

        # 运行 handler 处理消息
        await run_handler_once()

        # 等待处理完成
        await asyncio.sleep(2)

        # 检查结果
        check_output_messages()
        check_reminders()
        check_future_messages()


async def test_future_message_trigger():
    """测试未来消息触发功能"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: 未来消息触发功能")
    logger.info("=" * 60)

    # 发送一条普通对话消息
    test_messages = [
        "你好，最近怎么样？",
        "今天天气真好",
    ]

    for msg in test_messages[:1]:  # 只测试第一条
        logger.info(f"\n发送测试消息: {msg}")
        send_test_message(msg)

        # 等待一下让消息入库
        await asyncio.sleep(1)

        # 运行 handler 处理消息
        await run_handler_once()

        # 等待处理完成
        await asyncio.sleep(2)

        # 检查结果
        check_output_messages()
        future = check_future_messages()

        if future and future.get("action"):
            logger.info("✓ 未来消息已规划!")
        else:
            logger.info("✗ 未来消息未规划 (可能是概率未命中)")


async def test_dialog_loop():
    """交互式对话测试循环"""
    logger.info("\n" + "=" * 60)
    logger.info("交互式对话测试")
    logger.info("=" * 60)
    logger.info("输入消息进行测试，输入 'quit' 退出")
    logger.info("特殊命令:")
    logger.info("  /status-查看当前状态")
    logger.info("  /clear-清理测试数据")
    logger.info("  /reminder-查看提醒列表")
    logger.info("  /future-查看未来消息规划")
    logger.info("  /bg-运行后台任务")
    logger.info("=" * 60)

    user = user_dao.get_user_by_id(from_user)
    user_name = user["platforms"]["wechat"]["nickname"]

    while True:
        try:
            input_text = input(f"\n{user_name}：")

            if input_text.lower() == "quit":
                break
            elif input_text == "/status":
                check_output_messages()
                check_reminders()
                check_future_messages()
                continue
            elif input_text == "/clear":
                clear_test_data()
                continue
            elif input_text == "/reminder":
                check_reminders()
                continue
            elif input_text == "/future":
                check_future_messages()
                continue
            elif input_text == "/bg":
                await run_background_handler_once()
                continue
            elif not input_text.strip():
                continue

            # 发送消息
            send_test_message(input_text)

            # 运行 handler
            await run_handler_once()

            # 等待处理
            await asyncio.sleep(1)

            # 显示回复
            messages = mongo.find_many(
                "outputmessages",
                {
                    "platform": "wechat",
                    "from_user": to_user,
                    "to_user": from_user,
                    "status": "pending",
                },
                limit=10,
            )

            character = user_dao.get_user_by_id(to_user)
            char_name = character["platforms"]["wechat"]["nickname"]

            for msg in messages:
                print(f"{char_name}：{msg.get('message', '')}")
                # 标记为已处理
                msg["status"] = "handled"
                mongo.replace_one("outputmessages", {"_id": msg["_id"]}, msg)

            # 检查是否创建了提醒
            reminders = reminder_dao.find_reminders_by_user(
                from_user, status="confirmed"
            )
            if reminders:
                logger.info(f"[系统] 检测到 {len(reminders)} 个新提醒")

            # 检查未来消息规划
            future = check_future_messages()
            if future and future.get("action"):
                logger.info(f"[系统] 未来消息已规划: {future.get('action')}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"错误: {e}")
            import traceback

            traceback.print_exc()


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="用户对话功能测试")
    parser.add_argument(
        "--mode",
        choices=["auto", "interactive", "reminder", "future"],
        default="interactive",
        help="测试模式",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("用户对话功能测试")
    logger.info("=" * 60)
    logger.info(f"测试用户: {from_user}")
    logger.info(f"测试角色: {to_user}")
    logger.info("=" * 60)

    if args.mode == "auto":
        # 自动测试
        await test_reminder_trigger()
        await test_future_message_trigger()
    elif args.mode == "reminder":
        await test_reminder_trigger()
    elif args.mode == "future":
        await test_future_message_trigger()
    else:
        # 交互式测试
        await test_dialog_loop()

    logger.info("\n测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
