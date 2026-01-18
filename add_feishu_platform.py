#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 qiaoyun 角色添加飞书平台支持"""

import sys
import os

# 确保路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dao.user_dao import UserDAO

def add_feishu_platform():
    """为 qiaoyun 角色添加 langbot_feishu 平台"""
    try:
        user_dao = UserDAO()

        # 查找 qiaoyun 角色
        characters = user_dao.find_characters({"name": "qiaoyun"})
        if not characters:
            print("✗ 错误: 未找到 qiaoyun 角色")
            return False

        char = characters[0]
        char_id = str(char["_id"])

        print("=== 当前配置 ===")
        print(f"角色名: {char.get('name')}")
        print(f"现有平台: {list(char.get('platforms', {}).keys())}")

        # 检查是否已有飞书平台
        platforms = char.get("platforms", {})
        if "langbot_feishu" in platforms:
            print("\n✓ 已存在 langbot_feishu 平台，无需添加")
            return True

        # 添加飞书平台
        print("\n=== 添加 langbot_feishu 平台 ===")
        platforms["langbot_feishu"] = {
            "id": "qiaoyun-feishu",
            "account": "qiaoyun-feishu",
            "nickname": "巧云",
            "name": "巧云"
        }

        # 更新到数据库
        user_dao.update_user(char_id, {"platforms": platforms})
        print("✓ 已更新数据库")

        # 验证更新结果
        updated_char = user_dao.get_user_by_id(char_id)
        print(f"\n=== 更新后的平台列表 ===")
        print(f"平台: {list(updated_char.get('platforms', {}).keys())}")

        return True

    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = add_feishu_platform()
    sys.exit(0 if success else 1)
