# -*- coding: utf-8 -*-
"""
Platform Adapters

具体平台适配器实现，支持多平台接入。
"""

from connector.adapters.discord.discord_adapter import DiscordAdapter

# Gateway 模式适配器
from connector.adapters.telegram.telegram_adapter import TelegramAdapter
from connector.adapters.terminal.terminal_adapter import TerminalAdapter

# Webhook 模式适配器
from connector.adapters.whatsapp.whatsapp_adapter import WhatsAppAdapter

__all__ = [
    # Gateway 适配器
    "TelegramAdapter",
    "DiscordAdapter",
    "TerminalAdapter",
    # Webhook 适配器
    "WhatsAppAdapter",
]
