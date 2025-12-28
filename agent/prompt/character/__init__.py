# -*- coding: utf-8 -*-
"""
角色系统提示词模块

每个角色有一个独立的 prompt 文件，包含其系统提示词。
这样可以：
- 使用 Git 进行版本控制
- 方便进行 prompt 微调和迭代
- 与其他 prompt 文件保持一致的管理方式
"""

from agent.prompt.character.coke_prompt import COKE_STATUS, COKE_SYSTEM_PROMPT

# 角色配置注册表
# key: 角色名称（与数据库中的 name 字段对应）
# value: (系统提示词, 状态配置)
CHARACTER_PROMPTS = {
    "coke": {
        "system_prompt": COKE_SYSTEM_PROMPT,
        "status": COKE_STATUS,
    },
    # 未来添加新角色时，在这里注册
    # "new_character": {
    #     "system_prompt": NEW_CHARACTER_SYSTEM_PROMPT,
    #     "status": NEW_CHARACTER_STATUS,
    # },
}


def get_character_prompt(character_name: str) -> str | None:
    """
    获取角色的系统提示词
    
    Args:
        character_name: 角色名称
        
    Returns:
        系统提示词字符串，如果角色不存在则返回 None
    """
    config = CHARACTER_PROMPTS.get(character_name.lower())
    if config:
        return config.get("system_prompt")
    return None


def get_character_status(character_name: str) -> dict | None:
    """
    获取角色的状态配置
    
    Args:
        character_name: 角色名称
        
    Returns:
        状态配置字典，如果角色不存在则返回 None
    """
    config = CHARACTER_PROMPTS.get(character_name.lower())
    if config:
        return config.get("status")
    return None
