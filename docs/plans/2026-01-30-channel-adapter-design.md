# Channel Adapter 统一接口设计

> 日期：2026-01-30
> 目标：规范化多平台接入，支持轮询 + Gateway 混合模式

> **DEPRECATED (2026-02-16):** LangBot integration has been removed. This document
> is kept for historical reference only. Future platform integrations will use
> alternative approaches.

---

## 一、设计目标

1. **规范化接口**：定义统一的 ChannelAdapter 接口
2. **混合模式**：支持轮询（现有）和 Gateway（新增）两种运行模式
3. **平滑过渡**：现有平台保持轮询，新平台使用 Gateway，后续逐步迁移
4. **平台覆盖**：
   - 保持：Ecloud (微信)、LangBot (Feishu/Telegram)
   - 新增：Moltbot 支持的平台 (Discord/Slack/WhatsApp/Signal 等)

---

## 二、架构概览

```
                         ┌─────────────────────────────────┐
                         │        ChannelRegistry          │
                         │   (渠道注册中心，统一管理)        │
                         └────────────────┬────────────────┘
                                          │
                 ┌────────────────────────┼────────────────────────┐
                 │                        │                        │
         ┌───────v───────┐       ┌────────v────────┐      ┌────────v────────┐
         │ PollingAdapter │       │ GatewayAdapter  │      │  (Future...)    │
         │   运行模式      │       │   运行模式       │      │                 │
         └───────┬───────┘       └────────┬────────┘      └─────────────────┘
                 │                        │
    ┌────────────┼────────────┐           │
    │            │            │           │
┌───v───┐  ┌─────v─────┐  ┌───v───┐  ┌────v────┐
│Ecloud │  │  LangBot  │  │Terminal│  │ Gateway │
│WeChat │  │Feishu/TG  │  │  Test  │  │WebSocket│
└───┬───┘  └─────┬─────┘  └───┬───┘  └────┬────┘
    │            │            │           │
    └────────────┼────────────┘           │
                 │                        │
         ┌───────v───────┐       ┌────────v────────┐
         │   MongoDB     │       │  In-Memory      │
         │  消息队列      │       │  事件队列        │
         └───────┬───────┘       └────────┬────────┘
                 │                        │
                 └────────────────────────┘
                              │
                   ┌──────────v──────────┐
                   │    Agent Handler    │
                   │   (统一消息处理)     │
                   └─────────────────────┘
```

---

## 三、核心接口定义

### 3.1 基础类型

```python
# connector/channel/types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Callable, Awaitable
from datetime import datetime


class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"
    REFERENCE = "reference"   # 引用/回复
    STICKER = "sticker"       # 表情包
    LOCATION = "location"     # 位置
    CONTACT = "contact"       # 联系人卡片


class ChatType(Enum):
    """会话类型"""
    PRIVATE = "private"       # 私聊
    GROUP = "group"           # 群聊
    CHANNEL = "channel"       # 频道 (Discord/Slack)


class DeliveryMode(Enum):
    """消息投递模式"""
    POLLING = "polling"       # 轮询 MongoDB
    GATEWAY = "gateway"       # Gateway 实时推送
    HYBRID = "hybrid"         # 混合模式


@dataclass
class ChannelCapabilities:
    """渠道能力声明"""
    # 支持的消息类型
    message_types: List[MessageType] = field(
        default_factory=lambda: [MessageType.TEXT]
    )
    # 支持的会话类型
    chat_types: List[ChatType] = field(
        default_factory=lambda: [ChatType.PRIVATE]
    )
    # 功能支持
    supports_mention: bool = False      # @提及
    supports_reply: bool = False        # 消息回复
    supports_reaction: bool = False     # 消息表情回应
    supports_edit: bool = False         # 消息编辑
    supports_delete: bool = False       # 消息撤回
    supports_thread: bool = False       # 消息线程
    supports_media_upload: bool = False # 媒体上传
    # 限制
    max_text_length: int = 4096         # 单条消息最大长度
    max_media_size_mb: int = 10         # 媒体文件最大大小


@dataclass
class StandardMessage:
    """标准消息格式"""
    # 基础字段
    message_id: Optional[str] = None    # 消息唯一 ID
    platform: str = ""                  # 平台标识
    chat_type: ChatType = ChatType.PRIVATE

    # 参与者
    from_user: str = ""                 # 发送者（平台用户 ID）
    from_user_db_id: Optional[str] = None  # 发送者（MongoDB ObjectId）
    to_user: str = ""                   # 接收者/角色（平台用户 ID）
    to_user_db_id: Optional[str] = None    # 接收者/角色（MongoDB ObjectId）
    chatroom_id: Optional[str] = None   # 群聊/频道 ID

    # 消息内容
    message_type: MessageType = MessageType.TEXT
    content: str = ""                   # 文本内容或媒体描述
    media_url: Optional[str] = None     # 媒体 URL
    media_data: Optional[bytes] = None  # 媒体二进制数据

    # 回复/引用
    reply_to_id: Optional[str] = None   # 回复的消息 ID
    reply_to_content: Optional[str] = None  # 回复的消息内容

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: int = 0                  # Unix 时间戳

    # 状态
    status: str = "pending"             # pending/handled/failed


@dataclass
class UserInfo:
    """用户信息"""
    platform_user_id: str               # 平台用户 ID
    db_user_id: Optional[str] = None    # MongoDB ObjectId
    display_name: Optional[str] = None  # 显示名称
    username: Optional[str] = None      # 用户名
    avatar_url: Optional[str] = None    # 头像 URL
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3.2 ChannelAdapter 接口

```python
# connector/channel/adapter.py

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncGenerator


class ChannelAdapter(ABC):
    """
    渠道适配器基类

    所有平台适配器都需要实现这个接口
    """

    # ==================== 基础属性 ====================

    @property
    @abstractmethod
    def channel_id(self) -> str:
        """
        渠道唯一标识

        示例: 'wechat', 'telegram', 'discord', 'slack'
        """
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """渠道显示名称"""
        pass

    @property
    @abstractmethod
    def delivery_mode(self) -> DeliveryMode:
        """消息投递模式: POLLING / GATEWAY / HYBRID"""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ChannelCapabilities:
        """声明渠道支持的能力"""
        pass

    # ==================== 消息转换 ====================

    @abstractmethod
    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        平台消息格式 → 标准消息格式

        Args:
            raw_message: 平台原始消息

        Returns:
            StandardMessage: 标准化消息
        """
        pass

    @abstractmethod
    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → 平台消息格式

        Args:
            message: 标准化消息

        Returns:
            Dict: 平台特定格式
        """
        pass

    # ==================== 消息发送 ====================

    @abstractmethod
    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到平台

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        pass

    async def send_text(self, to_user: str, text: str, **kwargs) -> bool:
        """便捷方法：发送文本消息"""
        msg = StandardMessage(
            platform=self.channel_id,
            to_user=to_user,
            message_type=MessageType.TEXT,
            content=text,
            **kwargs
        )
        return await self.send_message(msg)

    async def send_media(
        self,
        to_user: str,
        media_type: MessageType,
        media_url: Optional[str] = None,
        media_data: Optional[bytes] = None,
        **kwargs
    ) -> bool:
        """便捷方法：发送媒体消息"""
        msg = StandardMessage(
            platform=self.channel_id,
            to_user=to_user,
            message_type=media_type,
            media_url=media_url,
            media_data=media_data,
            **kwargs
        )
        return await self.send_message(msg)

    # ==================== 用户解析 ====================

    @abstractmethod
    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析平台用户信息

        Args:
            platform_user_id: 平台用户 ID

        Returns:
            UserInfo: 用户信息，找不到返回 None
        """
        pass

    async def resolve_or_create_user(
        self,
        platform_user_id: str,
        default_name: Optional[str] = None
    ) -> UserInfo:
        """解析用户，不存在则创建"""
        user = await self.resolve_user(platform_user_id)
        if user:
            return user
        # 创建新用户（子类可覆盖）
        return UserInfo(
            platform_user_id=platform_user_id,
            display_name=default_name or platform_user_id
        )

    # ==================== 群组支持（可选） ====================

    def is_mentioned(self, message: StandardMessage, bot_id: str) -> bool:
        """
        检测消息是否 @了机器人

        Args:
            message: 标准消息
            bot_id: 机器人的平台 ID

        Returns:
            bool: 是否被提及
        """
        return False

    def should_respond_in_group(
        self,
        message: StandardMessage,
        config: Dict[str, Any]
    ) -> bool:
        """
        群聊回复策略

        Args:
            message: 标准消息
            config: 配置（包含白名单、回复模式等）

        Returns:
            bool: 是否应该回复
        """
        return True

    def strip_mention(self, text: str) -> str:
        """
        去除文本中的 @提及

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        return text

    # ==================== 生命周期（可选） ====================

    async def start(self):
        """启动适配器（如建立连接）"""
        pass

    async def stop(self):
        """停止适配器（如关闭连接）"""
        pass

    async def health_check(self) -> bool:
        """健康检查"""
        return True
```

### 3.3 Polling 模式适配器

```python
# connector/channel/polling_adapter.py

from abc import abstractmethod
from typing import List, Optional


class PollingAdapter(ChannelAdapter):
    """
    轮询模式适配器基类

    适用于：Ecloud (微信)、LangBot (Feishu/Telegram)、Terminal
    """

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.POLLING

    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = poll_interval

    # ==================== 轮询特有方法 ====================

    @abstractmethod
    async def poll_messages(self) -> List[StandardMessage]:
        """
        轮询获取新消息

        Returns:
            List[StandardMessage]: 新消息列表
        """
        pass

    @abstractmethod
    async def poll_and_send(self) -> int:
        """
        轮询并发送待发消息

        Returns:
            int: 发送的消息数量
        """
        pass

    # ==================== 与现有系统集成 ====================

    async def input_handler(self):
        """兼容现有 BaseConnector.input_handler"""
        messages = await self.poll_messages()
        for msg in messages:
            await self._save_to_input_queue(msg)

    async def output_handler(self):
        """兼容现有 BaseConnector.output_handler"""
        await self.poll_and_send()

    async def _save_to_input_queue(self, message: StandardMessage):
        """保存消息到 MongoDB inputmessages"""
        from dao.mongo import MongoDBBase
        mongo = MongoDBBase()
        doc = {
            "input_timestamp": message.timestamp,
            "handled_timestamp": None,
            "status": "pending",
            "from_user": message.from_user_db_id,
            "platform": message.platform,
            "chatroom_name": message.chatroom_id,
            "to_user": message.to_user_db_id,
            "message_type": message.message_type.value,
            "message": message.content,
            "metadata": message.metadata,
        }
        mongo.insert_one("inputmessages", doc)
```

### 3.4 Gateway 模式适配器

```python
# connector/channel/gateway_adapter.py

from abc import abstractmethod
from typing import Optional, Callable, Awaitable, AsyncGenerator
import asyncio


class GatewayAdapter(ChannelAdapter):
    """
    Gateway 模式适配器基类

    适用于：Discord、Slack、WhatsApp、Signal 等新增平台
    """

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.GATEWAY

    def __init__(self):
        self._message_handler: Optional[Callable[[StandardMessage], Awaitable[None]]] = None
        self._connected = False

    # ==================== 连接管理 ====================

    @abstractmethod
    async def connect(self):
        """建立与平台的连接（如 WebSocket）"""
        pass

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected

    # ==================== 消息流 ====================

    def on_message(self, handler: Callable[[StandardMessage], Awaitable[None]]):
        """
        注册消息处理回调

        Args:
            handler: 异步回调函数，接收 StandardMessage
        """
        self._message_handler = handler

    async def _emit_message(self, message: StandardMessage):
        """内部方法：触发消息处理"""
        if self._message_handler:
            await self._message_handler(message)

    # ==================== 生命周期 ====================

    async def start(self):
        """启动适配器"""
        await self.connect()
        self._connected = True

    async def stop(self):
        """停止适配器"""
        await self.disconnect()
        self._connected = False
```

---

## 四、Gateway 服务设计

### 4.1 Gateway Server

```python
# connector/gateway/server.py

import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from connector.channel.adapter import ChannelAdapter, StandardMessage
from connector.channel.gateway_adapter import GatewayAdapter


@dataclass
class GatewayConfig:
    """Gateway 配置"""
    host: str = "0.0.0.0"
    port: int = 8765
    heartbeat_interval: float = 30.0
    reconnect_delay: float = 5.0


class GatewayServer:
    """
    Gateway 服务器

    管理所有 Gateway 模式的渠道适配器
    """

    def __init__(self, config: GatewayConfig = None):
        self.config = config or GatewayConfig()
        self._adapters: Dict[str, GatewayAdapter] = {}
        self._running = False
        self._message_queue: asyncio.Queue[StandardMessage] = asyncio.Queue()

    # ==================== 适配器管理 ====================

    def register_adapter(self, adapter: GatewayAdapter):
        """注册 Gateway 适配器"""
        if adapter.channel_id in self._adapters:
            raise ValueError(f"Adapter {adapter.channel_id} already registered")

        # 设置消息回调
        adapter.on_message(self._on_adapter_message)
        self._adapters[adapter.channel_id] = adapter

    def unregister_adapter(self, channel_id: str):
        """注销适配器"""
        if channel_id in self._adapters:
            del self._adapters[channel_id]

    def get_adapter(self, channel_id: str) -> Optional[GatewayAdapter]:
        """获取适配器"""
        return self._adapters.get(channel_id)

    # ==================== 消息处理 ====================

    async def _on_adapter_message(self, message: StandardMessage):
        """适配器消息回调"""
        await self._message_queue.put(message)

    async def _message_processor(self):
        """消息处理循环"""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0
                )
                await self._process_message(message)
            except asyncio.TimeoutError:
                continue

    async def _process_message(self, message: StandardMessage):
        """
        处理单条消息

        这里调用 Agent Handler
        """
        from agent.runner.message_processor import process_message
        await process_message(message)

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
            return False

        return await adapter.send_message(message)

    # ==================== 生命周期 ====================

    async def start(self):
        """启动 Gateway 服务"""
        self._running = True

        # 启动所有适配器
        for adapter in self._adapters.values():
            await adapter.start()

        # 启动消息处理循环
        asyncio.create_task(self._message_processor())

    async def stop(self):
        """停止 Gateway 服务"""
        self._running = False

        # 停止所有适配器
        for adapter in self._adapters.values():
            await adapter.stop()

    async def health_check(self) -> Dict[str, bool]:
        """健康检查所有适配器"""
        results = {}
        for channel_id, adapter in self._adapters.items():
            results[channel_id] = await adapter.health_check()
        return results
```

---

## 五、渠道注册中心

```python
# connector/channel/registry.py

from typing import Dict, List, Optional, Type
from connector.channel.adapter import ChannelAdapter, DeliveryMode
from connector.channel.polling_adapter import PollingAdapter
from connector.channel.gateway_adapter import GatewayAdapter


class ChannelRegistry:
    """
    渠道注册中心

    统一管理所有渠道适配器
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters: Dict[str, ChannelAdapter] = {}
        return cls._instance

    def register(self, adapter: ChannelAdapter):
        """注册适配器"""
        self._adapters[adapter.channel_id] = adapter

    def unregister(self, channel_id: str):
        """注销适配器"""
        if channel_id in self._adapters:
            del self._adapters[channel_id]

    def get(self, channel_id: str) -> Optional[ChannelAdapter]:
        """获取适配器"""
        return self._adapters.get(channel_id)

    def list_all(self) -> List[ChannelAdapter]:
        """列出所有适配器"""
        return list(self._adapters.values())

    def list_by_mode(self, mode: DeliveryMode) -> List[ChannelAdapter]:
        """按投递模式列出"""
        return [a for a in self._adapters.values() if a.delivery_mode == mode]

    def list_polling(self) -> List[PollingAdapter]:
        """列出所有轮询模式适配器"""
        return [a for a in self._adapters.values()
                if isinstance(a, PollingAdapter)]

    def list_gateway(self) -> List[GatewayAdapter]:
        """列出所有 Gateway 模式适配器"""
        return [a for a in self._adapters.values()
                if isinstance(a, GatewayAdapter)]


# 全局单例
channel_registry = ChannelRegistry()
```

---

## 六、实施计划

### Phase 1: 接口定义 (1-2 天)
- [ ] 创建 `connector/channel/` 目录结构
- [ ] 实现 `types.py` (基础类型)
- [ ] 实现 `adapter.py` (ChannelAdapter 基类)
- [ ] 实现 `polling_adapter.py` (PollingAdapter)
- [ ] 实现 `gateway_adapter.py` (GatewayAdapter)
- [ ] 实现 `registry.py` (ChannelRegistry)

### Phase 2: Gateway 服务 (1-2 天)
- [ ] 实现 Gateway Server 基础框架
- [ ] 实现消息分发机制
- [ ] 与 Agent Handler 集成

### Phase 3: P0 平台接入 (3-4 天)
- [ ] **Telegram 适配器** (Gateway 模式)
  - 使用 python-telegram-bot 库
  - 实现消息收发
  - 支持文本/图片/语音
- [ ] **Discord 适配器** (Gateway 模式)
  - 使用 discord.py 库
  - 实现消息收发
  - 支持文本/图片/语音

### Phase 4: 现有适配器迁移 (可选，后续)
- [ ] 迁移 Ecloud 适配器到新接口
- [ ] 迁移 LangBot 适配器到新接口
- [ ] 迁移 Terminal 适配器到新接口

---

## 七、目录结构

```
connector/
├── channel/                    # 新增：统一接口层
│   ├── __init__.py
│   ├── types.py               # 基础类型定义
│   ├── adapter.py             # ChannelAdapter 基类
│   ├── polling_adapter.py     # PollingAdapter 基类
│   ├── gateway_adapter.py     # GatewayAdapter 基类
│   └── registry.py            # 渠道注册中心
│
├── gateway/                    # 新增：Gateway 服务
│   ├── __init__.py
│   ├── server.py              # Gateway Server
│   └── config.py              # Gateway 配置
│
├── adapters/                   # 新增：具体适配器实现
│   ├── __init__.py
│   ├── ecloud/                # WeChat (迁移自 ecloud/)
│   ├── langbot/               # Feishu/Telegram (迁移自 langbot/)
│   ├── terminal/              # Terminal (迁移自 terminal/)
│   ├── discord/               # 新增：Discord
│   ├── slack/                 # 新增：Slack
│   └── ...
│
├── base_connector.py          # 保留：向后兼容
├── ecloud/                    # 保留：逐步迁移
├── langbot/                   # 保留：逐步迁移
└── terminal/                  # 保留：逐步迁移
```

---

## 八、配置结构

```json
{
  "channels": {
    "registry": {
      "enabled_channels": ["wechat", "telegram", "discord"]
    },
    "wechat": {
      "adapter": "ecloud",
      "mode": "polling",
      "poll_interval": 1.0,
      "config": {
        "wId": { "coke": "wxid_xxx" }
      }
    },
    "telegram": {
      "adapter": "langbot",
      "mode": "polling",
      "poll_interval": 1.0,
      "config": {
        "bot_token": "xxx"
      }
    },
    "discord": {
      "adapter": "discord",
      "mode": "gateway",
      "config": {
        "bot_token": "xxx",
        "guild_ids": ["123", "456"]
      }
    }
  },
  "gateway": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8765,
    "heartbeat_interval": 30
  }
}
```

---

## 九、下一步行动

1. **确认设计** - 审阅本文档，确认方向
2. **创建骨架** - 实现基础接口和类型
3. **迁移第一个适配器** - 从 Terminal 开始（最简单）
4. **添加第一个 Gateway 适配器** - Discord（生态成熟）

---

## 附录：平台接入优先级

| 平台 | 优先级 | 运行模式 | 说明 |
|------|-------|---------|------|
| **Telegram** | **P0** | Gateway | 直接对接 Telegram Bot API |
| **Discord** | **P0** | Gateway | 使用 discord.py 库 |
| WeChat | 保持 | Polling | 现有 Ecloud 适配器 |
| Feishu | 保持 | Polling | 现有 LangBot 适配器 |
| Slack | P1 | Gateway | 后续扩展 |
| Signal | P1 | Gateway | 后续扩展 |
| WhatsApp | P2 | Gateway | 需要 Business API |
| MS Teams | P2 | Gateway | 后续扩展 |
