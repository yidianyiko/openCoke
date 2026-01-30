# -*- coding: utf-8 -*-
"""
Gateway 服务器

管理所有 Gateway 模式的渠道适配器，提供实时消息处理服务。
"""

import asyncio
from typing import Dict, Optional

from util.log_util import get_logger

from connector.channel.adapter import ChannelAdapter, StandardMessage
from connector.channel.gateway_adapter import GatewayAdapter
from connector.gateway.config import GatewayConfig

logger = get_logger(__name__)


class GatewayServer:
    """
    Gateway 服务器

    管理所有 Gateway 模式的渠道适配器
    """

    def __init__(self, config: Optional[GatewayConfig] = None):
        """
        初始化 Gateway 服务

        Args:
            config: Gateway 配置
        """
        self.config = config or GatewayConfig()
        self._adapters: Dict[str, GatewayAdapter] = {}
        self._running = False
        self._message_queue: asyncio.Queue[StandardMessage] = asyncio.Queue()
        self._processor_task: Optional[asyncio.Task] = None
        self._adapters_tasks: Dict[str, asyncio.Task] = {}

    # ==================== 适配器管理 ====================

    def register_adapter(self, adapter: GatewayAdapter):
        """
        注册 Gateway 适配器

        Args:
            adapter: Gateway 适配器实例

        Raises:
            ValueError: 适配器 ID 已存在
        """
        if adapter.channel_id in self._adapters:
            raise ValueError(f"Adapter {adapter.channel_id} already registered")

        # 设置消息回调
        adapter.on_message(self._on_adapter_message)
        self._adapters[adapter.channel_id] = adapter
        logger.info(f"Gateway 注册适配器: {adapter.channel_id}")

    def unregister_adapter(self, channel_id: str):
        """
        注销适配器

        Args:
            channel_id: 渠道 ID
        """
        if channel_id in self._adapters:
            del self._adapters[channel_id]
            logger.info(f"Gateway 注销适配器: {channel_id}")

    def get_adapter(self, channel_id: str) -> Optional[GatewayAdapter]:
        """
        获取适配器

        Args:
            channel_id: 渠道 ID

        Returns:
            GatewayAdapter: 适配器实例，不存在返回 None
        """
        return self._adapters.get(channel_id)

    def list_adapters(self) -> Dict[str, GatewayAdapter]:
        """
        列出所有适配器

        Returns:
            Dict[str, GatewayAdapter]: 适配器字典
        """
        return self._adapters.copy()

    # ==================== 消息处理 ====================

    async def _on_adapter_message(self, message: StandardMessage):
        """
        适配器消息回调

        Args:
            message: 标准消息
        """
        await self._message_queue.put(message)
        logger.debug(
            f"Gateway 收到消息: platform={message.platform}, "
            f"from_user={message.from_user}, content={message.content[:50]}"
        )

    async def _message_processor(self):
        """消息处理循环"""
        logger.info("Gateway 消息处理器启动")
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(), timeout=1.0
                )
                await self._process_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Gateway 消息处理异常: {e}")
        logger.info("Gateway 消息处理器停止")

    async def _process_message(self, message: StandardMessage):
        """
        处理单条消息

        将 Gateway 消息转换为 MongoDB inputmessages 格式，
        复用现有的消息处理流程。

        Args:
            message: 标准消息
        """
        from dao.mongo import MongoDBBase
        from entity.message import save_inputmessage
        from util.time_util import get_current_timestamp

        mongo = MongoDBBase()

        # 解析用户（从平台 ID 到 MongoDB ObjectId）
        user_id = await self._resolve_user_id(message.platform, message.from_user)
        character_id = await self._resolve_character_id(
            message.platform, message.to_user
        )

        if not user_id or not character_id:
            logger.warning(
                f"无法解析用户或角色: platform={message.platform}, "
                f"from_user={message.from_user}, to_user={message.to_user}"
            )
            return

        # 构建 inputmessages 文档
        doc = {
            "input_timestamp": message.timestamp or get_current_timestamp(),
            "handled_timestamp": None,
            "status": "pending",
            "from_user": user_id,
            "platform": message.platform,
            "chatroom_name": message.chatroom_id,
            "to_user": character_id,
            "message_type": message.message_type.value,
            "message": message.content,
            "metadata": message.metadata,
        }

        # 保存到 MongoDB
        save_inputmessage(doc)
        logger.info(
            f"Gateway 消息已保存: platform={message.platform}, "
            f"message_id={doc.get('_id')}"
        )

    async def _resolve_user_id(self, platform: str, platform_user_id: str) -> Optional[str]:
        """
        解析平台用户 ID 为 MongoDB ObjectId

        Args:
            platform: 平台标识
            platform_user_id: 平台用户 ID

        Returns:
            Optional[str]: MongoDB ObjectId，找不到返回 None
        """
        from dao.user_dao import UserDAO

        user_dao = UserDAO()
        user = user_dao.find_user_by_platform_id(platform, platform_user_id)
        return str(user["_id"]) if user else None

    async def _resolve_character_id(
        self, platform: str, platform_character_id: str
    ) -> Optional[str]:
        """
        解析平台角色 ID 为 MongoDB ObjectId

        Args:
            platform: 平台标识
            platform_character_id: 平台角色 ID

        Returns:
            Optional[str]: MongoDB ObjectId，找不到返回 None
        """
        from dao.user_dao import UserDAO

        user_dao = UserDAO()
        character = user_dao.find_character_by_platform_id(platform, platform_character_id)
        return str(character["_id"]) if character else None

    # ==================== 发送消息 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        通过 Gateway 发送消息

        Args:
            message: 标准消息

        Returns:
            bool: 是否发送成功
        """
        adapter = self._adapters.get(message.platform)
        if not adapter:
            logger.warning(f"找不到适配器: {message.platform}")
            return False

        if not adapter.is_connected:
            logger.warning(f"适配器未连接: {message.platform}")
            return False

        try:
            return await adapter.send_message(message)
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    async def send_text(
        self, platform: str, to_user: str, text: str, **kwargs
    ) -> bool:
        """
        便捷方法：发送文本消息

        Args:
            platform: 平台标识
            to_user: 接收者（平台用户 ID）
            text: 文本内容
            **kwargs: 其他消息参数

        Returns:
            bool: 是否发送成功
        """
        adapter = self._adapters.get(platform)
        if not adapter:
            return False
        return await adapter.send_text(to_user, text, **kwargs)

    # ==================== 生命周期 ====================

    async def start(self):
        """启动 Gateway 服务"""
        if self._running:
            logger.warning("Gateway 服务已在运行")
            return

        self._running = True
        logger.info("Gateway 服务启动中...")

        # 启动所有适配器
        for channel_id, adapter in self._adapters.items():
            try:
                await adapter.start()
                logger.info(f"适配器启动成功: {channel_id}")
            except Exception as e:
                logger.error(f"适配器启动失败 {channel_id}: {e}")

        # 启动消息处理循环
        self._processor_task = asyncio.create_task(self._message_processor())

        logger.info(f"Gateway 服务已启动 (监听 {len(self._adapters)} 个适配器)")

    async def stop(self):
        """停止 Gateway 服务"""
        if not self._running:
            return

        self._running = False
        logger.info("Gateway 服务停止中...")

        # 停止消息处理循环
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        # 停止所有适配器
        for channel_id, adapter in self._adapters.items():
            try:
                await adapter.stop()
                logger.info(f"适配器已停止: {channel_id}")
            except Exception as e:
                logger.error(f"适配器停止失败 {channel_id}: {e}")

        logger.info("Gateway 服务已停止")

    async def health_check(self) -> Dict[str, bool]:
        """
        健康检查所有适配器

        Returns:
            Dict[str, bool]: 各适配器的健康状态
        """
        results = {}
        for channel_id, adapter in self._adapters.items():
            try:
                results[channel_id] = await adapter.health_check()
            except Exception as e:
                logger.error(f"健康检查失败 {channel_id}: {e}")
                results[channel_id] = False
        return results

    # ==================== 状态查询 ====================

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    @property
    def adapter_count(self) -> int:
        """已注册的适配器数量"""
        return len(self._adapters)

    @property
    def queue_size(self) -> int:
        """消息队列大小"""
        return self._message_queue.qsize()


# 全局单例
_gateway_server: Optional[GatewayServer] = None


def get_gateway_server() -> GatewayServer:
    """
    获取全局 Gateway 服务器实例

    Returns:
        GatewayServer: Gateway 服务器实例
    """
    global _gateway_server
    if _gateway_server is None:
        _gateway_server = GatewayServer()
    return _gateway_server
