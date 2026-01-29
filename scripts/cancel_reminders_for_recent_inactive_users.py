#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
取消为最近不活跃用户设置的提醒

此脚本用于将指定用户的活动提醒状态更新为已完成，以避免继续提醒不活跃用户
"""

import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

sys.path.append(".")

from dao.reminder_dao import ReminderDAO


def update_user_reminders_to_completed(
    user_ids: List[str], reminder_dao: ReminderDAO
) -> Dict[str, int]:
    """
    将指定用户的所有活动提醒更新为已完成状态

    Args:
        user_ids: 用户ID列表
        reminder_dao: ReminderDAO实例

    Returns:
        Dict[str, int]: 每个用户更新的提醒数量
    """
    results = {}

    for user_id in user_ids:
        # 获取用户的所有活动提醒
        active_reminders = reminder_dao.find_reminders_by_user(
            user_id=user_id, status="active"
        )

        updated_count = 0
        for reminder in active_reminders:
            reminder_id = reminder.get("reminder_id")
            if reminder_id:
                # 更新提醒状态为已完成
                success = reminder_dao.update_reminder(
                    reminder_id, {"status": "completed", "updated_at": int(time.time())}
                )
                if success:
                    updated_count += 1

        results[user_id] = updated_count
        print(f"用户 {user_id}: 更新了 {updated_count} 个提醒为已完成状态")

    return results


def main():
    """主函数"""
    print("🔧 批量取消最近不活跃用户的提醒")
    print("=" * 60)

    # 3天内未发送消息但仍有未触发提醒的用户ID列表
    inactive_user_ids = [
        "693e8cad16773b825cfaa47e",  # 3.6天前，1个提醒
        "6946061df09e7d5a55ad9f53",  # 3.0天前，1个提醒
        "69460f7bf09e7d5a55ad9fb0",  # 3.6天前，2个提醒
        "69461098f09e7d5a55ad9fb6",  # 3.3天前，3个提醒
    ]

    print(f"总共需要处理 {len(inactive_user_ids)} 个用户")

    # 初始化数据库连接
    reminder_dao = ReminderDAO()

    try:
        # 更新所有指定用户的提醒状态
        results = update_user_reminders_to_completed(inactive_user_ids, reminder_dao)

        # 统计总数
        total_updated = sum(results.values())
        print(f"\n✅ 完成! 总共更新了 {total_updated} 个提醒的状态为已完成")

        # 显示详细结果
        print("\n详细结果:")
        for user_id, count in results.items():
            if count > 0:
                print(f"  用户 {user_id}: {count} 个提醒已设置为不再提醒")

    finally:
        reminder_dao.close()


if __name__ == "__main__":
    main()
