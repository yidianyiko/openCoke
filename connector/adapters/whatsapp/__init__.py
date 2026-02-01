# -*- coding: utf-8 -*-
"""
WhatsApp 适配器模块

提供两种 WhatsApp 集成方式：
1. EvolutionAdapter: 使用 Evolution API (基于 Baileys，无需 Meta 开发者账号)
2. WhatsAppAdapter: 使用官方 WhatsApp Cloud API (需要 Meta 开发者账号)

推荐使用 EvolutionAdapter，因为：
- 不需要 Meta 开发者账号
- 支持 QR 码登录
- 没有官方 API 的 24 小时回复窗口限制
- 完全免费

Evolution API 文档: https://doc.evolution-api.com/
"""

from connector.adapters.whatsapp.evolution_adapter import EvolutionAdapter

__all__ = [
    "EvolutionAdapter",
]

# 向后兼容：旧的 WhatsAppAdapter (Cloud API) 仍可导入
from connector.adapters.whatsapp.whatsapp_adapter import WhatsAppAdapter  # noqa: F401
