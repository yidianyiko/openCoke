# -*- coding: utf-8 -*-
"""
Platform Adapters

当前仓库保留的本地适配器入口。
"""

from connector.adapters.discord.discord_adapter import DiscordAdapter
from connector.adapters.telegram.telegram_adapter import TelegramAdapter
from connector.adapters.terminal.terminal_adapter import TerminalAdapter

__all__ = [
    "TelegramAdapter",
    "DiscordAdapter",
    "TerminalAdapter",
]
