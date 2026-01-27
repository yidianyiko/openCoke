#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
为角色用户添加 LangBot 平台信息的脚本

此脚本用于为所有角色用户添加 LangBot 平台信息，确保它们能够处理来自 LangBot 的消息。
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)

def add_langbot_platform_to_characters():
    """
    为所有角色用户添加 LangBot 平台信息
    """
    user_dao = UserDAO()
    
    # 查找所有角色用户
    characters = user_dao.find_characters({})
    
    updated_count = 0
    
    for character in characters:
        character_id = str(character["_id"])
        character_name = character.get("name", f"character_{character_id}")
        platforms = character.get("platforms", {})
        
        # 为每个可能的 LangBot 平台添加信息
        # 这里我们先添加基础的 langbot 信息，实际使用时会根据具体适配器添加相应字段
        langbot_platforms = [key for key in platforms.keys() if key.startswith("langbot_")]
        
        if not langbot_platforms:
            # 如果角色没有任何 LangBot 平台信息，添加一个通用的
            logger.info(f"角色 {character_name} 缺少 LangBot 平台信息，添加基础信息...")
            # 为了演示目的，我们添加一个示例平台信息
            # 实际应用中，可能需要为每个支持的适配器都添加相应信息
            user_dao.add_platform_to_user(
                character_id,
                "langbot_LarkAdapter",  # 示例：为飞书适配器添加平台信息
                {
                    "id": character.get("name", f"char_{character_id}"),
                    "nickname": character.get("name", f"Character"),
                    "account": character.get("name", f"char_{character_id}")
                }
            )
            updated_count += 1
            logger.info(f"已为角色 {character_name} 添加 langbot_LarkAdapter 平台信息")
        else:
            logger.info(f"角色 {character_name} 已有 LangBot 平台信息: {langbot_platforms}")
    
    logger.info(f"处理完成，共为 {updated_count} 个角色用户添加了 LangBot 平台信息")

def add_specific_platform_to_character(character_id: str, platform_name: str, platform_data: dict):
    """
    为特定角色添加特定平台信息
    
    Args:
        character_id: 角色用户ID
        platform_name: 平台名称，如 'langbot_LarkAdapter'
        platform_data: 平台数据
    """
    user_dao = UserDAO()
    
    success = user_dao.add_platform_to_user(character_id, platform_name, platform_data)
    
    if success:
        logger.info(f"成功为角色 {character_id} 添加 {platform_name} 平台信息")
    else:
        logger.error(f"为角色 {character_id} 添加 {platform_name} 平台信息失败")
    
    return success

if __name__ == "__main__":
    logger.info("开始为角色用户添加 LangBot 平台信息...")
    
    add_langbot_platform_to_characters()
    
    logger.info("处理完成！")