# -*- coding: utf-8 -*-
"""
Webhook HTTP 服务器

为 Webhook 模式适配器提供 HTTP 端点接收推送。
"""

import asyncio
from typing import Awaitable, Callable, Dict, Optional

from aiohttp import web

from connector.channel.types import StandardMessage
from connector.channel.webhook_adapter import WebhookAdapter
from util.log_util import get_logger

logger = get_logger(__name__)


class WebhookServer:
    """
    Webhook HTTP 服务器

    管理所有 Webhook 适配器的 HTTP 端点
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        """
        初始化 Webhook 服务器

        Args:
            host: 监听地址
            port: 监听端口
        """
        self.host = host
        self.port = port
        self._adapters: Dict[str, WebhookAdapter] = {}
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._running = False

    # ==================== 适配器管理 ====================

    def register_adapter(self, adapter: WebhookAdapter):
        """
        注册 Webhook 适配器

        Args:
            adapter: Webhook 适配器实例
        """
        path = adapter.webhook_path.lstrip("/")
        self._adapters[path] = adapter
        logger.info(f"Webhook 注册适配器: {adapter.channel_id} -> /{path}")

    def unregister_adapter(self, channel_id: str):
        """
        注销适配器

        Args:
            channel_id: 渠道 ID
        """
        # 通过 channel_id 查找并删除
        for path, adapter in list(self._adapters.items()):
            if adapter.channel_id == channel_id:
                del self._adapters[path]
                logger.info(f"Webhook 注销适配器: {channel_id}")

    def get_adapter(self, path: str) -> Optional[WebhookAdapter]:
        """
        获取适配器

        Args:
            path: Webhook 路径

        Returns:
            WebhookAdapter: 适配器实例
        """
        return self._adapters.get(path.lstrip("/"))

    # ==================== 消息处理回调 ====================

    def on_message(self, handler: Callable[[StandardMessage], Awaitable[None]]):
        """
        设置统一的消息处理回调

        Args:
            handler: 消息处理函数
        """
        for adapter in self._adapters.values():
            adapter.on_message(handler)

    # ==================== HTTP 路由 ====================

    async def _handle_webhook_get(self, request: web.Request) -> web.Response:
        """
        处理 Webhook 验证请求 (GET)

        WhatsApp 验证流程：
        1. Meta 发送 GET 请求到 webhook URL
        2. 包含 hub.mode, hub.verify_token, hub.challenge
        3. 验证成功返回 challenge
        """
        path = request.path.lstrip("/")
        adapter = self.get_adapter(path)

        if not adapter:
            logger.warning(f"未找到适配器: {path}")
            return web.Response(status=404, text="Not Found")

        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        result = await adapter.verify_webhook(mode, token, challenge)

        if result:
            logger.info(f"Webhook 验证成功: {path}")
            return web.Response(status=200, text=result)
        else:
            logger.warning(f"Webhook 验证失败: {path}")
            return web.Response(status=403, text="Forbidden")

    async def _handle_webhook_post(self, request: web.Request) -> web.Response:
        """
        处理 Webhook 推送请求 (POST)

        消息推送流程：
        1. Meta 发送 POST 请求到 webhook URL
        2. 请求体包含消息数据
        3. 可选：验证 X-Hub-Signature-256 签名
        """
        path = request.path.lstrip("/")
        adapter = self.get_adapter(path)

        if not adapter:
            logger.warning(f"未找到适配器: {path}")
            return web.Response(status=404, text="Not Found")

        # 验证签名（如果配置了 app_secret）
        signature = request.headers.get("X-Hub-Signature-256", "")
        if signature and hasattr(adapter, "verify_signature"):
            payload = await request.read()
            if not adapter.verify_signature(payload, signature):
                logger.warning(f"Webhook 签名验证失败: {path}")
                return web.Response(status=403, text="Invalid Signature")
            # 解析 JSON
            try:
                data = json.loads(payload.decode())
            except json.JSONDecodeError:
                return web.Response(status=400, text="Invalid JSON")
        else:
            # 直接解析 JSON
            data = await request.json()

        # 处理 Webhook
        try:
            await adapter.handle_webhook(data)
            return web.Response(status=200, text="OK")
        except Exception as e:
            logger.error(f"Webhook 处理异常: {e}")
            return web.Response(status=500, text="Internal Error")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """健康检查端点"""
        status = {
            "running": self._running,
            "adapters": [
                {
                    "channel_id": adapter.channel_id,
                    "path": adapter.webhook_path,
                    "running": adapter.is_running,
                }
                for adapter in self._adapters.values()
            ],
        }
        return web.json_response(status)

    # ==================== 服务器生命周期 ====================

    async def start(self):
        """启动 Webhook 服务器"""
        if self._running:
            logger.warning("Webhook 服务器已在运行")
            return

        # 创建应用
        self._app = web.Application()

        # 注册路由
        # 动态路由，匹配所有路径
        self._app.router.add_route("GET", "/{path:.*}", self._handle_webhook_get)
        self._app.router.add_route("POST", "/{path:.*}", self._handle_webhook_post)
        self._app.router.add_get("/health", self._handle_health)

        # 启动适配器
        for adapter in self._adapters.values():
            await adapter.start()

        # 创建 Runner
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # 创建 Site
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        self._running = True
        logger.info(f"Webhook 服务器已启动: http://{self.host}:{self.port}")
        logger.info(f"注册的端点: {list(self._adapters.keys())}")

    async def stop(self):
        """停止 Webhook 服务器"""
        if not self._running:
            return

        self._running = False
        logger.info("Webhook 服务器停止中...")

        # 停止适配器
        for adapter in self._adapters.values():
            await adapter.stop()

        # 停止服务器
        if self._site:
            await self._site.stop()
            self._site = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        logger.info("Webhook 服务器已停止")

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    @property
    def adapter_count(self) -> int:
        """已注册的适配器数量"""
        return len(self._adapters)


# 全局单例
_webhook_server: Optional[WebhookServer] = None


def get_webhook_server() -> WebhookServer:
    """
    获取全局 Webhook 服务器实例

    Returns:
        WebhookServer: Webhook 服务器实例
    """
    global _webhook_server
    if _webhook_server is None:
        _webhook_server = WebhookServer()
    return _webhook_server


# 导入 json 用于签名验证
import json
