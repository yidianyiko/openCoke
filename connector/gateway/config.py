# -*- coding: utf-8 -*-
"""
Gateway 配置模块

定义 Gateway 服务的配置数据类。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GatewayConfig:
    """
    Gateway 配置

    Attributes:
        host: 监听地址
        port: 监听端口
        heartbeat_interval: 心跳间隔（秒）
        reconnect_delay: 重连延迟（秒）
        max_retries: 最大重试次数
        enabled: 是否启用 Gateway 服务
    """

    host: str = "0.0.0.0"
    port: int = 8765
    heartbeat_interval: float = 30.0
    reconnect_delay: float = 5.0
    max_retries: int = 3
    enabled: bool = True

    @classmethod
    def from_dict(cls, config_dict: dict) -> "GatewayConfig":
        """
        从字典创建配置

        Args:
            config_dict: 配置字典

        Returns:
            GatewayConfig: 配置实例
        """
        return cls(
            host=config_dict.get("host", "0.0.0.0"),
            port=config_dict.get("port", 8765),
            heartbeat_interval=config_dict.get("heartbeat_interval", 30.0),
            reconnect_delay=config_dict.get("reconnect_delay", 5.0),
            max_retries=config_dict.get("max_retries", 3),
            enabled=config_dict.get("enabled", True),
        )

    def to_dict(self) -> dict:
        """
        转换为字典

        Returns:
            dict: 配置字典
        """
        return {
            "host": self.host,
            "port": self.port,
            "heartbeat_interval": self.heartbeat_interval,
            "reconnect_delay": self.reconnect_delay,
            "max_retries": self.max_retries,
            "enabled": self.enabled,
        }
