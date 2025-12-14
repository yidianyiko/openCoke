#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 wxid_pw0fqky1nsj721 用户的 Content Exists Risk 问题

问题根因：relationship.description 字段过长（5932字符），累积了大量监督关系进展记录，
触发了 DeepSeek API 的内容安全审核。

解决方案：将关系描述精简为核心信息。

Usage:
    python scripts/fix_content_risk_user.py
"""

import sys
sys.path.append(".")

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO

# Target user wxid
TARGET_WXID = "wxid_pw0fqky1nsj721"

def main():
    print("=" * 60)
    print("修复 Content Exists Risk 问题")
    print(f"目标用户: {TARGET_WXID}")
    print("=" * 60)
    
    user_dao = UserDAO()
    mongo = MongoDBBase()
    
    # Get user
    user = user_dao.get_user_by_platform('wechat', TARGET_WXID)
    if not user:
        print(f"❌ 用户未找到: {TARGET_WXID}")
        return
    
    user_id = str(user['_id'])
    print(f"用户ID: {user_id}")
    
    # Get relation
    relation = mongo.find_one('relations', {'uid': user_id})
    if not relation:
        print("❌ 关系记录未找到")
        return
    
    old_desc = relation.get('relationship', {}).get('description', '')
    print(f"旧描述长度: {len(old_desc)} 字符")
    
    # 简化为基础描述（只保留核心信息）
    new_desc = '在微信上认识的新朋友，通过持续的学习监督互动建立了良好的协作关系，用户具有较强的自主学习能力和时间管理意识。'
    
    print(f"新描述: {new_desc}")
    print(f"新描述长度: {len(new_desc)} 字符")
    
    # 更新
    result = mongo.update_one(
        'relations', 
        {'_id': relation['_id']}, 
        {'$set': {'relationship.description': new_desc}}
    )
    
    print("=" * 60)
    print("✅ 已成功更新 relationship.description")
    print("=" * 60)
    
    # 验证
    updated_relation = mongo.find_one('relations', {'uid': user_id})
    updated_desc = updated_relation.get('relationship', {}).get('description', '')
    print(f"验证 - 更新后描述长度: {len(updated_desc)} 字符")
    print(f"验证 - 更新后描述内容: {updated_desc}")


if __name__ == "__main__":
    main()
