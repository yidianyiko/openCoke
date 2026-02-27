# -*- coding: utf-8 -*-
"""
终端聊天客户端-模拟微信聊天界面

功能：
- 输入消息发送给AI角色
- 实时显示AI角色的回复
- 支持测试未来消息和提醒功能
"""
import sys

sys.path.append(".")

import os
import threading
import time
from datetime import datetime

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from entity.message import save_outputmessage
from util.redis_client import RedisClient
from util.redis_stream import publish_input_event

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None

# ========== 配置 ==========
# 用户 ID（发送消息的人）
USER_ID = "692c14aaa538f0baad5561b3"  # 不辣的皮皮
# 角色 ID（AI 角色）
CHARACTER_ID = "692c147e972f64f2b65da6ee"  # qiaoyun (与 config.json 中 default_character_alias 一致)

# ========== 初始化 ==========
mongo = MongoDBBase()
user_dao = UserDAO()
redis_conf = RedisClient.from_config()
redis_client = (
    redis.Redis(host=redis_conf.host, port=redis_conf.port, db=redis_conf.db)
    if redis is not None
    else None
)

user = user_dao.get_user_by_id(USER_ID)
character = user_dao.get_user_by_id(CHARACTER_ID)

USER_NAME = user["platforms"]["wechat"]["nickname"] if user else "用户"
CHARACTER_NAME = character["platforms"]["wechat"]["nickname"] if character else "角色"

# 控制输出线程
running = True
last_output_time = 0


def clear_screen():
    """清屏"""
    os.system("clear" if os.name == "posix" else "cls")


def print_header():
    """打印聊天头部"""
    print("\n" + "=" * 50)
    print(f"  💬 终端聊天-与 {CHARACTER_NAME} 对话")
    print("=" * 50)
    print(f"  用户: {USER_NAME}")
    print(f"  角色: {CHARACTER_NAME}")
    print("-" * 50)
    print("  输入消息后按回车发送")
    print("  输入 'quit' 或 'exit' 退出")
    print("  输入 'clear' 清屏")
    print("=" * 50 + "\n")


def format_time(timestamp):
    """格式化时间"""
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def send_message(text):
    """发送消息到 inputmessages"""
    now = int(time.time())
    message = {
        "input_timestamp": now,
        "handled_timestamp": now,
        "status": "pending",
        "from_user": USER_ID,
        "platform": "wechat",
        "chatroom_name": None,
        "to_user": CHARACTER_ID,
        "message_type": "text",
        "message": text,
        "metadata": {},
    }
    inserted_id = mongo.insert_one("inputmessages", message)
    if redis_client is not None:
        publish_input_event(
            redis_client,
            inserted_id,
            message.get("platform", "wechat"),
            now,
            stream_key=redis_conf.stream_key,
        )
    return now


def check_output_messages():
    """检查并显示输出消息（在后台线程运行）"""
    global running, last_output_time

    while running:
        try:
            now = int(time.time())

            # 查找待发送的消息
            messages = mongo.find_many(
                "outputmessages",
                {
                    "platform": "wechat",
                    "from_user": CHARACTER_ID,
                    "to_user": USER_ID,
                    "status": "pending",
                    "expect_output_timestamp": {"$lte": now},
                },
            )

            for message in messages:
                # 显示消息
                msg_time = format_time(message.get("expect_output_timestamp", now))
                msg_type = message.get("message_type", "text")
                content = message.get("message", "")

                # 根据消息类型显示
                if msg_type == "voice":
                    print(f"\n  [{msg_time}] {CHARACTER_NAME}: 🎤 [语音] {content}")
                elif msg_type == "image":
                    print(f"\n  [{msg_time}] {CHARACTER_NAME}: 🖼️ [图片]")
                else:
                    print(f"\n  [{msg_time}] {CHARACTER_NAME}: {content}")

                # 检查是否有未来消息规划
                if message.get("source") == "proactive_message":
                    print("        📢 [主动消息]")
                elif message.get("source") == "reminder":
                    print("        ⏰ [提醒消息]")

                print()  # 空行

                # 标记为已处理
                message["status"] = "handled"
                message["handled_timestamp"] = now
                save_outputmessage(message)

                last_output_time = now

        except Exception:
            pass  # 忽略错误，继续运行

        time.sleep(0.5)  # 每0.5秒检查一次


def main():
    """主函数"""
    global running

    clear_screen()
    print_header()

    # 启动输出监听线程
    output_thread = threading.Thread(target=check_output_messages, daemon=True)
    output_thread.start()

    print("  [系统] 聊天已启动，等待输入...\n")

    try:
        while True:
            # 获取用户输入
            try:
                user_input = input(f"  {USER_NAME}: ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            # 处理特殊命令
            if user_input.lower() in ["quit", "exit", "q"]:
                print("\n  [系统] 正在退出...\n")
                break

            if user_input.lower() == "clear":
                clear_screen()
                print_header()
                continue

            if user_input.lower() == "help":
                print("\n  [帮助]")
                print("   -直接输入消息发送给角色")
                print("   -试试说 '提醒我5分钟后喝水' 测试提醒功能")
                print("   -试试说 '晚安' 测试未来消息功能")
                print("   -输入 'clear' 清屏")
                print("   -输入 'quit' 退出\n")
                continue

            # 发送消息
            send_time = send_message(user_input)
            print(f"        [{format_time(send_time)}] ✓ 已发送\n")

    except KeyboardInterrupt:
        print("\n\n  [系统] 收到中断信号，正在退出...\n")

    finally:
        running = False
        time.sleep(0.5)
        mongo.close()
        user_dao.close()
        print("  [系统] 聊天已结束\n")


if __name__ == "__main__":
    main()
