# -*- coding: utf-8 -*-
"""
Channel Adapter 基础类型定义

定义统一的消息类型、会话类型、投递模式和相关数据结构。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageType(Enum):
    """消息类型"""

    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"
    REFERENCE = "reference"  # 引用/回复
    STICKER = "sticker"  # 表情包
    LOCATION = "location"  # 位置
    CONTACT = "contact"  # 联系人卡片


class ChatType(Enum):
    """会话类型"""

    PRIVATE = "private"  # 私聊
    GROUP = "group"  # 群聊
    CHANNEL = "channel"  # 频道 (Discord/Slack)


class DeliveryMode(Enum):
    """消息投递模式"""

    POLLING = "polling"  # 轮询 MongoDB
    GATEWAY = "gateway"  # Gateway 实时推送
    HYBRID = "hybrid"  # 混合模式


@dataclass
class ChannelCapabilities:
    """渠道能力声明"""

    # 支持的消息类型
    message_types: List[MessageType] = field(default_factory=lambda: [MessageType.TEXT])
    # 支持的会话类型
    chat_types: List[ChatType] = field(default_factory=lambda: [ChatType.PRIVATE])
    # 功能支持
    supports_mention: bool = False  # @提及
    supports_reply: bool = False  # 消息回复
    supports_reaction: bool = False  # 消息表情回应
    supports_edit: bool = False  # 消息编辑
    supports_delete: bool = False  # 消息撤回
    supports_thread: bool = False  # 消息线程
    supports_media_upload: bool = False  # 媒体上传
    # 限制
    max_text_length: int = 4096  # 单条消息最大长度
    max_media_size_mb: int = 10  # 媒体文件最大大小


@dataclass
class StandardMessage:
    """标准消息格式"""

    # 基础字段
    message_id: Optional[str] = None  # 消息唯一 ID
    platform: str = ""  # 平台标识
    chat_type: ChatType = ChatType.PRIVATE

    # 参与者
    from_user: str = ""  # 发送者（平台用户 ID）
    from_user_db_id: Optional[str] = None  # 发送者（MongoDB ObjectId）
    to_user: str = ""  # 接收者/角色（平台用户 ID）
    to_user_db_id: Optional[str] = None  # 接收者/角色（MongoDB ObjectId）
    chatroom_id: Optional[str] = None  # 群聊/频道 ID

    # 消息内容
    message_type: MessageType = MessageType.TEXT
    content: str = ""  # 文本内容或媒体描述
    media_url: Optional[str] = None  # 媒体 URL
    media_data: Optional[bytes] = None  # 媒体二进制数据

    # 回复/引用
    reply_to_id: Optional[str] = None  # 回复的消息 ID
    reply_to_content: Optional[str] = None  # 回复的消息内容

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: int = 0  # Unix 时间戳

    # 状态
    status: str = "pending"  # pending/handled/failed


@dataclass
class UserInfo:
    """用户信息"""

    platform_user_id: str  # 平台用户 ID
    db_user_id: Optional[str] = None  # MongoDB ObjectId
    display_name: Optional[str] = None  # 显示名称
    username: Optional[str] = None  # 用户名
    avatar_url: Optional[str] = None  # 头像 URL
    metadata: Dict[str, Any] = field(default_factory=dict)
