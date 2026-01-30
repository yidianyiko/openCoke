# -*- coding: utf-8 -*-
"""
Onboarding Prompt - 新用户引导提示词

仅在用户首次与角色对话时注入，通过 is_new_user 标志控制。

使用方式：
    from agent.prompt.onboarding_prompt import get_onboarding_context

    onboarding_context = get_onboarding_context(context.get("is_new_user", False))
"""

# Onboarding 流程提示词（从 prepare_character.py 中提取）
ONBOARDING_PROMPT = """
<onboarding_and_first_dialogue>
        这是你与用户的首次对话，你必须执行以下 onboarding 流程，且回复必须简洁且分多条微信消息(不可以超过三条)发送：

        1. 首先热情打招呼并自我介绍.示例："Hii, 你好！我是Coke, 你的监督员.你希望我怎么称呼你？最近想要完成点什么吗？"

        2. 简短地告诉用户如何使用：
        a) 计划提醒
        b) 日常提醒
        c) 过程监督

        注意：必须保持微信消息的简洁风格，将问题和解释拆分成短小的几条消息(不可以超过三条)，而非一次性发送长段落.
</onboarding_and_first_dialogue>
"""


def get_onboarding_context(is_new_user: bool) -> str:
    """
    获取 Onboarding 上下文提示词

    Args:
        is_new_user: 是否为新用户（首次对话）

    Returns:
        如果是新用户，返回 onboarding 提示词；否则返回空字符串
    """
    if is_new_user:
        return ONBOARDING_PROMPT
    return ""
