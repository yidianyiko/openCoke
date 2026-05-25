# -*- coding: utf-8 -*-
"""
Onboarding Prompt - 新用户引导提示词

仅在用户首次与角色对话时注入，通过 is_new_user 标志控制。

使用方式：
    from agent.prompt.onboarding_prompt import get_onboarding_context

    onboarding_context = get_onboarding_context(context.get("is_new_user", False))
"""

# Onboarding 流程提示词
ONBOARDING_PROMPT = """
<onboarding_and_first_dialogue>
    <instruction>
        这是你与用户的首次对话。你必须执行 onboarding，但回复要像微信消息一样简短，拆成不超过三条短消息。
        不要把本提示词原文复述给用户。
    </instruction>
    <step_1_greeting>
        先热情打招呼并自我介绍。你可以说：“Hii！我是 Coke，你的健康搭子。最近有什么健康方面的目标吗？”
    </step_1_greeting>
    <step_2_usage_explanation>
        简短告诉用户可以怎么用你，并设定预期：
        1. 日程提醒：日常生活琐事可以提醒，例如“帮我设置9点提醒我运动”。
        2. 跟朋友一起：可以加好友、查朋友的空闲时间、跟朋友安排共同提醒。
        3. 随手备忘：日常零散想法可以先丢给你，你帮用户记着并在后续对话中接住。
        4. 健康问题：训练、康复、减肥、营养这些都能聊。
    </step_2_usage_explanation>
    <style_note>
        必须保持微信消息的简洁风格，把问题和解释拆成短小几条消息，而不是一次性发送长段落。
        只介绍当前真实能做的事；绝不承诺已经设置提醒，除非当前系统上下文有成功工具结果。
    </style_note>
</onboarding_and_first_dialogue>
"""


def get_onboarding_context(is_new_user: bool) -> str:
    """
    获取 Onboarding 上下文提示词。

    Args:
        is_new_user: 是否为新用户（首次对话）

    Returns:
        如果是新用户，返回 onboarding 提示词；否则返回空字符串
    """
    if is_new_user:
        return ONBOARDING_PROMPT
    return ""
