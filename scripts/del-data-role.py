#!/usr/bin/env python3
"""
用户数据清理脚本
完整删除指定用户及其所有关联数据
"""

import sys

sys.path.append(".")

from pprint import pprint

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO


def delete_user_completely(user_identifier: str):
    """
    完整删除用户及其所有关联数据

    Args:
        user_identifier: 用户ID (ObjectId) 或平台ID (如 wxid_xxx)
    """
    print(f"开始清理用户: {user_identifier}")
    print("=" * 60)

    # 步骤1: 查找并删除用户主记录
    print("\n[步骤1] 查找并删除用户主记录...")
    udao = UserDAO()

    # 尝试通过 ObjectId 查找
    doc = None
    try:
        doc = udao.get_user_by_id(user_identifier)
    except (TypeError, ValueError):
        pass

    # 如果没找到，尝试通过微信ID查找
    if not doc:
        doc = udao.get_user_by_platform("wechat", user_identifier)

    if not doc:
        print(f"❌ 用户 {user_identifier} 不存在")
        return False

    user_id = str(doc.get("_id"))
    wechat_id = doc.get("platforms", {}).get("wechat", {}).get("id")

    print("✓ 找到用户:")
    print(f" -姓名: {doc.get('name')}")
    print(f" -ObjectId: {user_id}")
    print(f" -微信ID: {wechat_id}")
    print(f" -微信昵称: {doc.get('platforms', {}).get('wechat', {}).get('nickname')}")
    print(f" -是否角色: {doc.get('is_character', False)}")

    ok = udao.delete_user(user_id)
    print(f"✓ 用户主记录删除: {'成功' if ok else '失败'}")

    # 步骤2: 检查关联数据
    print("\n[步骤2] 检查关联数据...")
    mongo = MongoDBBase()

    # 使用 ObjectId 和 wechat_id 查询
    relations_count = (
        mongo.count_documents("relations", {"uid": wechat_id}) if wechat_id else 0
    )
    conversations_count = (
        mongo.count_documents("conversations", {"talkers.id": wechat_id})
        if wechat_id
        else 0
    )
    input_from_count = (
        mongo.count_documents("inputmessages", {"from_user": wechat_id})
        if wechat_id
        else 0
    )
    input_to_count = (
        mongo.count_documents("inputmessages", {"to_user": wechat_id})
        if wechat_id
        else 0
    )

    stats = {
        "relations": relations_count,
        "conversations_with_user": conversations_count,
        "inputmessages_from": input_from_count,
        "inputmessages_to": input_to_count,
    }

    print("关联数据统计:")
    pprint(stats)

    # 步骤3: 清理关联数据
    print("\n[步骤3] 清理关联数据...")

    # 删除关系记录（使用 wechat_id）
    rel_deleted = 0
    if wechat_id:
        rel_deleted = mongo.delete_many("relations", {"uid": wechat_id})
    print(f"✓ 删除关系记录: {rel_deleted} 条")

    # 从会话参与者中移除（使用 wechat_id）
    mod_convs = 0
    if wechat_id:
        mod_convs = mongo.update_many(
            "conversations", {}, {"$pull": {"talkers": {"id": wechat_id}}}
        )
    print(f"✓ 修改会话记录: {mod_convs} 条")

    # 删除消息记录（使用 wechat_id）
    in_from_deleted = 0
    in_to_deleted = 0
    if wechat_id:
        in_from_deleted = mongo.delete_many("inputmessages", {"from_user": wechat_id})
        in_to_deleted = mongo.delete_many("inputmessages", {"to_user": wechat_id})
    print(f"✓ 删除发送消息: {in_from_deleted} 条")
    print(f"✓ 删除接收消息: {in_to_deleted} 条")

    # 步骤4: 验证清理结果
    print("\n[步骤4] 验证清理结果...")
    doc_after = udao.get_user_by_id(user_id)

    if doc_after:
        print("❌ 用户记录仍然存在")
        return False

    print("✓ 用户记录已完全删除")

    # 汇总
    print("\n" + "=" * 60)
    print("清理完成!")
    print("总计删除:")
    print(" -用户记录: 1 条")
    print(f" -关系记录: {rel_deleted} 条")
    print(f" -会话修改: {mod_convs} 条")
    print(f" -消息记录: {in_from_deleted + in_to_deleted} 条")
    print("=" * 60)

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python delete_user.py <user_identifier>")
        print("示例: python delete_user.py wxid_58bfckbpioh822")
        print("     python delete_user.py 69174a09005d9a476b7729ad")
        sys.exit(1)

    user_identifier = sys.argv[1]

    # 确认操作
    confirm = input(f"确认要删除用户 {user_identifier} 及其所有数据吗? (yes/no): ")
    if confirm.lower() != "yes":
        print("操作已取消")
        sys.exit(0)

    success = delete_user_completely(user_identifier)
    sys.exit(0 if success else 1)
