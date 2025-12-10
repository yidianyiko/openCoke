#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试脚本：检查 context_retrieve 数据填充问题

用法：
python debug_context_retrieve.py
"""

import asyncio
import logging
from dao.get_special_users import get_special_users

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def debug_context_retrieve():
    """调试 context_retrieve 数据"""
    
    # 1. 获取特殊用户
    logger.info("=" * 80)
    logger.info("Step 1: 获取特殊用户")
    logger.info("=" * 80)
    
    characters, admin_user = get_special_users()
    
    if not characters:
        logger.error("未找到特殊用户")
        return
    
    character = characters[0]
    logger.info(f"角色名称: {character.get('name')}")
    logger.info(f"角色ID: {character.get('_id')}")
    logger.info(f"微信昵称: {character.get('platforms', {}).get('wechat', {}).get('nickname')}")
    
    # 2. 测试 context_retrieve_tool
    logger.info("\n" + "=" * 80)
    logger.info("Step 2: 测试 context_retrieve_tool")
    logger.info("=" * 80)
    
    from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
    
    character_id = str(character.get('_id'))
    user_id = str(admin_user.get('_id')) if admin_user else ""
    
    logger.info(f"character_id: {character_id}")
    logger.info(f"user_id: {user_id}")
    
    # 测试检索
    result = context_retrieve_tool(
        character_setting_query="日常习惯",
        character_setting_keywords="作息,习惯",
        user_profile_query="基本信息",
        user_profile_keywords="姓名,工作",
        character_knowledge_query="专业技能",
        character_knowledge_keywords="心理学,GTD",
        character_id=character_id,
        user_id=user_id
    )
    
    logger.info("\n检索结果:")
    logger.info(f"character_global: {result.get('character_global', '')[:200]}...")
    logger.info(f"character_private: {result.get('character_private', '')[:200]}...")
    logger.info(f"user: {result.get('user', '')[:200]}...")
    logger.info(f"character_knowledge: {result.get('character_knowledge', '')[:200]}...")
    logger.info(f"confirmed_reminders: {result.get('confirmed_reminders', '')[:200]}...")
    
    # 3. 测试模板渲染
    logger.info("\n" + "=" * 80)
    logger.info("Step 3: 测试模板渲染")
    logger.info("=" * 80)
    
    from agent.prompt.chat_contextprompt import CONTEXTPROMPT_人物资料, CONTEXTPROMPT_用户资料
    
    # 构建 session_state
    session_state = {
        "character": character,
        "user": admin_user or {},
        "context_retrieve": result
    }
    
    try:
        rendered_character = CONTEXTPROMPT_人物资料.format(**session_state)
        logger.info(f"\n渲染后的角色资料:\n{rendered_character}")
    except KeyError as e:
        logger.error(f"渲染角色资料失败: {e}")
    
    try:
        rendered_user = CONTEXTPROMPT_用户资料.format(**session_state)
        logger.info(f"\n渲染后的用户资料:\n{rendered_user}")
    except KeyError as e:
        logger.error(f"渲染用户资料失败: {e}")
    
    # 4. 检查数据库中的数据
    logger.info("\n" + "=" * 80)
    logger.info("Step 4: 检查数据库中的角色设定数据")
    logger.info("=" * 80)
    
    from dao.character_setting_dao import CharacterSettingDAO
    from dao.user_profile_dao import UserProfileDAO
    from dao.character_knowledge_dao import CharacterKnowledgeDAO
    
    character_setting_dao = CharacterSettingDAO()
    user_profile_dao = UserProfileDAO()
    character_knowledge_dao = CharacterKnowledgeDAO()
    
    # 检查角色设定
    character_settings = character_setting_dao.get_character_settings(character_id)
    logger.info(f"\n角色设定数量: {len(character_settings) if character_settings else 0}")
    if character_settings:
        for i, setting in enumerate(character_settings[:3]):
            logger.info(f"  设定 {i+1}: {setting.get('key', '')} = {setting.get('value', '')[:100]}...")
    
    # 检查用户资料
    if user_id:
        user_profiles = user_profile_dao.get_user_profiles(user_id)
        logger.info(f"\n用户资料数量: {len(user_profiles) if user_profiles else 0}")
        if user_profiles:
            for i, profile in enumerate(user_profiles[:3]):
                logger.info(f"  资料 {i+1}: {profile.get('key', '')} = {profile.get('value', '')[:100]}...")
    
    # 检查角色知识
    character_knowledges = character_knowledge_dao.get_character_knowledges(character_id)
    logger.info(f"\n角色知识数量: {len(character_knowledges) if character_knowledges else 0}")
    if character_knowledges:
        for i, knowledge in enumerate(character_knowledges[:3]):
            logger.info(f"  知识 {i+1}: {knowledge.get('key', '')} = {knowledge.get('value', '')[:100]}...")
    
    logger.info("\n" + "=" * 80)
    logger.info("调试完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(debug_context_retrieve())
