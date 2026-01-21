#!/usr/bin/env python3
"""检查 LangBot 平台配置。

用于部署前验证，确保 config.json 中的 bots 配置正确，
且对应的角色在数据库中存在。
"""

import json
import sys

sys.path.append(".")

from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)


def check_langbot_config():
    """检查 LangBot 配置。"""
    print("=" * 60)
    print("LangBot 平台配置检查")
    print("=" * 60)

    issues = []

    # 1. 检查 config.json
    print("\n【配置文件检查】")
    try:
        with open("conf/config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print("  ❌ conf/config.json 不存在")
        return False
    except json.JSONDecodeError as e:
        print(f"  ❌ conf/config.json 解析失败: {e}")
        return False

    langbot_conf = config.get("langbot", {})

    # 检查 langbot 是否启用
    if not langbot_conf.get("enabled", False):
        print("  ⚠️  langbot.enabled = false，LangBot 未启用")
        print("  ✓ 跳过其他检查")
        return True

    print("  ✓ langbot.enabled = true")

    # 2. 检查 bots 配置
    print("\n【Bots 配置检查】")
    bots = langbot_conf.get("bots", {})

    if not bots:
        print("  ⚠️  未配置任何 bot")
        print("  提示: 在 config.json 的 langbot.bots 中添加 bot 配置")
        issues.append("未配置任何 bot")
    else:
        print(f"  ✓ 已配置 {len(bots)} 个 bot")

        for bot_key, bot_config in bots.items():
            print(f"\n  [{bot_key}]")
            bot_uuid = bot_config.get("bot_uuid", "")
            character = bot_config.get("character", "")

            # 检查 bot_uuid
            if not bot_uuid or bot_uuid == "YOUR_BOT_UUID_HERE":
                print(f"    ❌ bot_uuid 未设置或为占位符")
                issues.append(f"bot '{bot_key}' 的 bot_uuid 未设置")
            else:
                print(f"    ✓ bot_uuid: {bot_uuid[:8]}...")

            # 检查 character
            if not character:
                print(f"    ❌ character 未设置")
                issues.append(f"bot '{bot_key}' 的 character 未设置")
            else:
                print(f"    ✓ character: {character}")

    # 3. 检查角色是否存在于数据库
    print("\n【数据库角色检查】")
    user_dao = UserDAO()

    characters_to_check = set()
    for bot_config in bots.values():
        char_name = bot_config.get("character")
        if char_name:
            characters_to_check.add(char_name)

    # 添加默认角色
    default_char = langbot_conf.get("default_character_alias")
    if default_char:
        characters_to_check.add(default_char)

    for char_name in characters_to_check:
        characters = user_dao.find_characters({"name": char_name})
        if characters:
            print(f"  ✓ 角色 '{char_name}' 存在于数据库")
        else:
            print(f"  ❌ 角色 '{char_name}' 不存在于数据库")
            issues.append(f"角色 '{char_name}' 不存在于数据库")

    # 4. 检查飞书配置（如果有飞书 bot）
    has_feishu_bot = any("feishu" in k.lower() for k in bots.keys())
    if has_feishu_bot:
        print("\n【飞书 API 配置检查】")
        feishu_conf = langbot_conf.get("feishu", {})
        if feishu_conf.get("app_id") and feishu_conf.get("app_secret"):
            print("  ✓ 飞书 app_id 和 app_secret 已配置")
        else:
            print("  ❌ 飞书 app_id 或 app_secret 未配置")
            issues.append("飞书 API 凭证未配置")

    # 汇总报告
    print("\n" + "=" * 60)
    print("检查结果汇总")
    print("=" * 60)

    if not issues:
        print("\n✅ 所有配置正常！")
        return True
    else:
        print("\n❌ 发现配置问题：\n")
        for issue in issues:
            print(f"  - {issue}")

        print("\n修复建议：")
        print("  1. 编辑 conf/config.json，在 langbot.bots 中配置 bot")
        print("  2. 从 LangBot 后台获取 bot_uuid 并填入配置")
        print("  3. 确保 character 名称与数据库中的角色名匹配")
        print("  4. 参考文档: doc/langbot_single_server_deployment.md")

        return False


def main():
    """主函数。"""
    try:
        success = check_langbot_config()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"检查失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
