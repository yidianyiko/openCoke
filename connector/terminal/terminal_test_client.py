# -*- coding: utf-8 -*-
"""
Terminal Test Client - 程序化终端测试客户端

用于 E2E 测试，模拟用户通过终端发送消息并等待 AI 响应。
与 agent_handler 配合使用，覆盖完整 LLM 调用链路。

使用方式：
    client = TerminalTestClient(user_id, character_id)
    responses = client.chat("你好")
    assert len(responses) > 0
"""
import sys
import time
from typing import Optional

sys.path.append(".")

from util.log_util import get_logger

logger = get_logger(__name__)

from dao.mongo import MongoDBBase
from entity.message import save_outputmessage


class TerminalTestClient:
    """
    程序化终端测试客户端

    通过 MongoDB 消息队列与 agent_handler 通信：
    - send(): 写入 inputmessages
    - wait_response(): 轮询 outputmessages
    - chat(): send + wait_response 组合
    """

    DEFAULT_TIMEOUT = 180  # 3 分钟
    POLL_INTERVAL = 1.0  # 轮询间隔

    def __init__(self, user_id: str, character_id: str, platform: str = "wechat"):
        """
        初始化测试客户端

        Args:
            user_id: 用户 ID（发送消息的人）
            character_id: 角色 ID（AI 角色）
            platform: 平台标识，默认 wechat
        """
        self.user_id = user_id
        self.character_id = character_id
        self.platform = platform
        self.mongo = MongoDBBase()
        self._last_send_time = 0

    def send(self, text: str, message_type: str = "text") -> str:
        """
        发送消息到 inputmessages

        Args:
            text: 消息内容
            message_type: 消息类型，默认 text

        Returns:
            插入的消息 ID
        """
        now = int(time.time())

        # 记录发送前已存在的输出消息 ID，用于后续过滤
        existing_output_ids = set()
        existing_outputs = list(
            self.mongo.db["outputmessages"].find(
                {
                    "platform": self.platform,
                    "from_user": self.character_id,
                    "to_user": self.user_id,
                }
            )
        )
        for msg in existing_outputs:
            existing_output_ids.add(str(msg.get("_id", "")))
        self._existing_output_ids = existing_output_ids

        message = {
            "input_timestamp": now,
            "handled_timestamp": now,
            "status": "pending",
            "from_user": self.user_id,
            "platform": self.platform,
            "chatroom_name": None,
            "to_user": self.character_id,
            "message_type": message_type,
            "message": text,
            "metadata": {},
        }

        message_id = self.mongo.insert_one("inputmessages", message)
        self._last_send_time = now
        logger.info(f"[TerminalTestClient] 发送消息: {text[:50]}... (id={message_id})")
        return str(message_id)

    def wait_response(
        self, timeout: int = DEFAULT_TIMEOUT, since_timestamp: Optional[int] = None
    ) -> list[dict]:
        """
        等待并获取响应消息

        Args:
            timeout: 超时时间（秒）
            since_timestamp: 只获取此时间戳之后的消息，默认使用上次发送时间

        Returns:
            响应消息列表
        """
        if since_timestamp is None:
            since_timestamp = self._last_send_time - 1  # 留 1 秒余量

        # 获取发送前已存在的消息 ID，用于过滤
        existing_ids = getattr(self, "_existing_output_ids", set())

        start_time = time.time()
        collected_ids = set()
        responses = []

        logger.info(f"[TerminalTestClient] 等待响应 (timeout={timeout}s)...")

        while time.time() - start_time < timeout:
            # 查询新的 pending 或 handled 消息
            messages = list(
                self.mongo.db["outputmessages"]
                .find(
                    {
                        "platform": self.platform,
                        "from_user": self.character_id,
                        "to_user": self.user_id,
                        "expect_output_timestamp": {"$gte": since_timestamp},
                    }
                )
                .sort("expect_output_timestamp", 1)
            )

            new_messages = []
            for msg in messages:
                msg_id = str(msg.get("_id", ""))
                # 跳过发送前已存在的消息（如之前创建的提醒）
                if msg_id in existing_ids:
                    continue
                if msg_id and msg_id not in collected_ids:
                    collected_ids.add(msg_id)
                    new_messages.append(msg)
                    responses.append(msg)
                    logger.info(
                        f"[TerminalTestClient] 收到响应: {msg.get('message', '')[:50]}..."
                    )

            # 检查是否有消息且最后一条已经可以输出（时间已到）
            if responses:
                now = int(time.time())
                last_msg = responses[-1]
                expect_time = last_msg.get("expect_output_timestamp", 0)

                # 如果最后一条消息的预期输出时间已过，且没有新消息，认为响应完成
                if expect_time <= now and not new_messages:
                    # 再等一个轮询周期确认没有更多消息
                    time.sleep(self.POLL_INTERVAL)
                    check_messages = list(
                        self.mongo.db["outputmessages"].find(
                            {
                                "platform": self.platform,
                                "from_user": self.character_id,
                                "to_user": self.user_id,
                                "expect_output_timestamp": {"$gte": since_timestamp},
                            }
                        )
                    )
                    if len(check_messages) == len(collected_ids):
                        logger.info(
                            f"[TerminalTestClient] 响应完成，共 {len(responses)} 条"
                        )
                        break

            time.sleep(self.POLL_INTERVAL)

        if not responses:
            logger.warning(f"[TerminalTestClient] 超时未收到响应")

        return responses

    def chat(self, text: str, timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
        """
        发送消息并等待响应（组合方法）

        Args:
            text: 消息内容
            timeout: 超时时间（秒）

        Returns:
            响应消息列表
        """
        self.send(text)
        return self.wait_response(timeout=timeout)

    def clear_pending_input(self):
        """清理该用户的所有 pending 输入消息"""
        result = self.mongo.update_many(
            "inputmessages",
            {
                "from_user": self.user_id,
                "to_user": self.character_id,
                "status": "pending",
            },
            {"$set": {"status": "canceled"}},
        )
        logger.info(f"[TerminalTestClient] 清理 pending 输入消息: {result}")

    def clear_pending_output(self):
        """清理该用户的所有 pending 输出消息"""
        result = self.mongo.update_many(
            "outputmessages",
            {
                "from_user": self.character_id,
                "to_user": self.user_id,
                "status": "pending",
            },
            {"$set": {"status": "canceled"}},
        )
        logger.info(f"[TerminalTestClient] 清理 pending 输出消息: {result}")

    def clear_all_pending(self):
        """清理所有 pending 消息"""
        self.clear_pending_input()
        self.clear_pending_output()

    def close(self):
        """关闭连接"""
        self.mongo.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
