#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断 Content Exists Risk 问题

逐步测试用户 wxid_pw0fqky1nsj721 的各个数据组件，
定位触发 DeepSeek API 内容安全审核的具体数据源.

Usage:
    python scripts/diagnose_content_risk.py

测试策略：
1. 测试基础连接（无用户数据）
2. 测试 chat_history（对话历史）
3. 测试 character profile（角色资料）
4. 测试 user profile（用户资料）
5. 测试 relation（关系数据）
6. 测试完整 context（组合测试）
"""

import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()
import asyncio

from util.log_util import get_logger

logger = get_logger(__name__)

from conf.config import CONF
from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO

# Target user wxid
TARGET_WXID = "wxid_pw0fqky1nsj721"

# Initialize DAOs
user_dao = UserDAO()
conversation_dao = ConversationDAO()
mongo = MongoDBBase()


def fetch_user_data(wxid: str):
    """获取指定 wxid 的用户数据"""
    user = user_dao.get_user_by_platform("wechat", wxid)
    if not user:
        logger.error(f"User not found: {wxid}")
        return None
    return user


def fetch_conversation_data(user_id: str, character_id: str):
    """获取用户和角色之间的对话数据"""
    conversations = conversation_dao.find_conversations_by_user(
        user_id, platform="wechat"
    )
    for conv in conversations:
        for talker in conv.get("talkers", []):
            if talker.get("id") == character_id or str(talker.get("id")) == str(
                character_id
            ):
                return conv
    return None


def fetch_relation_data(user_id: str, character_id: str):
    """获取用户和角色之间的关系数据"""
    relation = mongo.find_one(
        "relations", {"uid": str(user_id), "cid": str(character_id)}
    )
    return relation


def fetch_character_data():
    """获取角色数据"""
    target_user_alias = CONF.get("default_character_alias", "coke")
    _characters_conf = (
        CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
    )
    target_wechat_id = _characters_conf.get(target_user_alias)

    characters = user_dao.find_characters({"platforms.wechat.id": target_wechat_id})
    if characters:
        return characters[0]
    return None


async def test_deepseek_api(prompt: str, test_name: str) -> bool:
    """
    测试 DeepSeek API 是否触发 Content Exists Risk

    Returns:
        True: 通过（无风险）
        False: 触发 Content Exists Risk
    """
    from agno.agent import Agent
    from agno.models.deepseek import DeepSeek

    logger.info(f"\n{'='*60}")
    logger.info(f"测试: {test_name}")
    logger.info(f"Prompt 长度: {len(prompt)} 字符")
    logger.info(f"{'='*60}")

    try:
        agent = Agent(
            id="content-risk-test",
            name="ContentRiskTest",
            model=DeepSeek(id="deepseek-chat"),
            markdown=False,
        )

        response = await agent.arun(input=prompt)

        logger.info(f"✅ {test_name}: 通过 (无 Content Risk)")
        return True

    except Exception as e:
        error_msg = str(e)
        if "Content Exists Risk" in error_msg:
            logger.error(f"❌ {test_name}: 触发 Content Exists Risk!")
            logger.error(f"   错误详情: {error_msg[:200]}...")
            return False
        else:
            logger.warning(f"⚠️ {test_name}: 其他错误-{error_msg[:100]}...")
            return True  # 非 content risk 错误，视为通过


async def run_diagnostic():
    """运行诊断测试"""
    print("\n" + "=" * 70)
    print("Content Exists Risk 诊断工具")
    print(f"目标用户: {TARGET_WXID}")
    print("=" * 70)

    # 1. 获取用户数据
    logger.info("\n[Step 1] 获取用户数据...")
    user = fetch_user_data(TARGET_WXID)
    if not user:
        logger.error("无法获取用户数据，终止诊断")
        return

    user_id = str(user["_id"])
    user_nickname = user.get("platforms", {}).get("wechat", {}).get("nickname", "未知")
    logger.info(f"用户ID: {user_id}, 昵称: {user_nickname}")

    # 2. 获取角色数据
    logger.info("\n[Step 2] 获取角色数据...")
    character = fetch_character_data()
    if not character:
        logger.error("无法获取角色数据，终止诊断")
        return

    character_id = str(character["_id"])
    character_nickname = (
        character.get("platforms", {}).get("wechat", {}).get("nickname", "未知")
    )
    character_wxid = character.get("platforms", {}).get("wechat", {}).get("id", "未知")
    logger.info(
        f"角色ID: {character_id}, 昵称: {character_nickname}, wxid: {character_wxid}"
    )

    # 3. 获取对话数据
    logger.info("\n[Step 3] 获取对话数据...")
    user_wxid = user.get("platforms", {}).get("wechat", {}).get("id", "")
    conversation = fetch_conversation_data(user_wxid, character_wxid)
    if not conversation:
        logger.warning("未找到对话数据，将使用空历史")
        conversation = {"conversation_info": {"chat_history": []}}
    else:
        chat_history = conversation.get("conversation_info", {}).get("chat_history", [])
        logger.info(f"对话历史条数: {len(chat_history)}")

    # 4. 获取关系数据
    logger.info("\n[Step 4] 获取关系数据...")
    relation = fetch_relation_data(user_id, character_id)
    if not relation:
        logger.warning("未找到关系数据")
        relation = {}
    else:
        logger.info(
            f"关系数据: closeness={relation.get('relationship', {}).get('closeness', 'N/A')}"
        )

    # 5. 开始测试
    print("\n" + "=" * 70)
    print("开始诊断测试...")
    print("=" * 70)

    results = {}

    # Test 0: 基础连接测试
    results["0_baseline"] = await test_deepseek_api(
        "你好，请用一句话回复", "基础连接测试（无用户数据）"
    )

    # Test 1: 测试 chat_history
    chat_history = conversation.get("conversation_info", {}).get("chat_history", [])
    if chat_history:
        chat_history_str = "\n".join(
            [
                f"{msg.get('from_nickname', '未知')}: {msg.get('message', '')}"
                for msg in chat_history[-20:]  # 最近20条
            ]
        )
        results["1_chat_history"] = await test_deepseek_api(
            f"以下是对话历史，请分析：\n{chat_history_str}\n\n请用一句话总结",
            f"对话历史测试（{len(chat_history[-20:])}条消息）",
        )

        # 如果对话历史有问题，进一步细分测试
        if not results["1_chat_history"]:
            logger.info("\n[细分测试] 逐步测试对话历史中的每5条消息...")
            for i in range(0, min(len(chat_history), 50), 5):
                chunk = chat_history[i : i + 5]
                chunk_str = "\n".join(
                    [
                        f"{msg.get('from_nickname', '未知')}: {msg.get('message', '')}"
                        for msg in chunk
                    ]
                )
                chunk_result = await test_deepseek_api(
                    f"对话片段：\n{chunk_str}\n请总结", f"对话历史片段 [{i}:{i + 5}]"
                )
                if not chunk_result:
                    logger.error(f"🔴 问题定位：对话历史第 {i} 到 {i + 5} 条消息")
                    # 打印问题消息的内容（部分）
                    for j, msg in enumerate(chunk):
                        content = msg.get("message", "")[:100]
                        logger.error(
                            f"   [{i + j}] {msg.get('from_nickname', '未知')}: {content}..."
                        )
    else:
        results["1_chat_history"] = True
        logger.info("跳过对话历史测试（无历史记录）")

    # Test 2: 测试 character profile（角色描述）
    char_description = character.get("user_info", {}).get("description", "")
    if char_description:
        results["2_character_description"] = await test_deepseek_api(
            f"角色描述：{char_description}\n请用一句话总结这个角色", "角色描述测试"
        )
    else:
        results["2_character_description"] = True
        logger.info("跳过角色描述测试（无描述）")

    # Test 3: 测试 relation 数据
    if relation:
        relation_str = """
关系描述：{relation.get('relationship', {}).get('description', '')}
用户真名：{relation.get('user_info', {}).get('realname', '')}
用户昵称：{relation.get('user_info', {}).get('hobbyname', '')}
用户印象：{relation.get('user_info', {}).get('description', '')}
角色态度：{relation.get('character_info', {}).get('attitude', '')}
短期目标：{relation.get('character_info', {}).get('shortterm_purpose', '')}
长期目标：{relation.get('character_info', {}).get('longterm_purpose', '')}
"""
        results["3_relation"] = await test_deepseek_api(
            f"关系信息：{relation_str}\n请用一句话总结", "关系数据测试"
        )

        # 细分关系数据测试
        if not results["3_relation"]:
            # 分别测试各个字段
            for field_name, field_value in [
                (
                    "relationship.description",
                    relation.get("relationship", {}).get("description", ""),
                ),
                (
                    "user_info.realname",
                    relation.get("user_info", {}).get("realname", ""),
                ),
                (
                    "user_info.hobbyname",
                    relation.get("user_info", {}).get("hobbyname", ""),
                ),
                (
                    "user_info.description",
                    relation.get("user_info", {}).get("description", ""),
                ),
                (
                    "character_info.attitude",
                    relation.get("character_info", {}).get("attitude", ""),
                ),
                (
                    "character_info.shortterm_purpose",
                    relation.get("character_info", {}).get("shortterm_purpose", ""),
                ),
                (
                    "character_info.longterm_purpose",
                    relation.get("character_info", {}).get("longterm_purpose", ""),
                ),
            ]:
                if field_value:
                    field_result = await test_deepseek_api(
                        f"{field_name}: {field_value}\n请总结",
                        f"关系字段测试: {field_name}",
                    )
                    if not field_result:
                        logger.error(f"🔴 问题定位：关系字段 {field_name}")
                        logger.error(f"   内容: {field_value[:200]}...")
    else:
        results["3_relation"] = True
        logger.info("跳过关系数据测试（无数据）")

    # Test 4: 组合测试（模拟 ChatWorkflow 的完整 prompt）
    full_prompt = """你是{character_nickname}，正在与{user_nickname}通过微信聊天.

### 角色描述
{char_description[:500] if char_description else '无'}

### 关系信息
{relation_str if relation else '无'}

### 历史对话
{chat_history_str if chat_history else '无历史记录'}

### 用户最新消息
你好

请根据以上信息回复用户.
"""
    results["4_full_context"] = await test_deepseek_api(
        full_prompt, "完整上下文组合测试"
    )

    # 6. 输出诊断结果
    print("\n" + "=" * 70)
    print("诊断结果汇总")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 触发 Content Risk"
        print(f"  {test_name}: {status}")

    # 找出问题组件
    failed_tests = [name for name, passed in results.items() if not passed]
    if failed_tests:
        print("\n" + "=" * 70)
        print("🔴 发现问题的数据组件:")
        print("=" * 70)
        for test in failed_tests:
            print(f" -{test}")
        print("\n建议:")
        print("  1. 检查上述组件中的敏感内容")
        print("  2. 使用 scripts/cleanup_sensitive_content.py 清理敏感词")
        print("  3. 手动检查数据库中该用户的相关记录")
    else:
        print("\n✅ 所有测试通过，未检测到明显的 Content Risk 来源")
        print("   可能是多个数据组合后触发，或者是动态生成的内容问题")


async def main():
    await run_diagnostic()


if __name__ == "__main__":
    asyncio.run(main())
