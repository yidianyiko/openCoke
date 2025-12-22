#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除特定重复提醒的脚本

此脚本用于删除特定的重复提醒：
用户 69460cdbf09e7d5a55ad9f94 在星期六晚上11点4分设置的两个相同提醒「站起来活动一下」

使用方法：
    python scripts/remove_specific_duplicate.py
"""

import sys
sys.path.append(".")

from dao.reminder_dao import ReminderDAO


def remove_specific_duplicate():
    """删除特定的重复提醒"""
    dao = ReminderDAO()
    
    try:
        # 定义要删除的提醒ID
        # 保留 interval 类型的提醒，删除单次类型的提醒
        reminder_id_to_delete = "be0193dd-ff4a-4470-aded-a88ac240b55c"  # 单次类型的提醒
        
        # 获取要删除的提醒信息
        reminder_to_delete = dao.get_reminder_by_id(reminder_id_to_delete)
        
        if not reminder_to_delete:
            print(f"未找到ID为 {reminder_id_to_delete} 的提醒")
            return False
        
        # 显示要删除的提醒信息
        print("要删除的提醒:")
        print(f"  ID: {reminder_to_delete.get('reminder_id')}")
        print(f"  用户: {reminder_to_delete.get('user_id')}")
        print(f"  标题: {reminder_to_delete.get('title')}")
        print(f"  时间: {reminder_to_delete.get('next_trigger_time')}")
        print(f"  类型: {reminder_to_delete.get('recurrence', {}).get('type', '单次')}")
        
        # 确认删除
        confirm = input("\n确认删除这个提醒吗? (y/N): ")
        if confirm.lower() != 'y':
            print("取消删除操作")
            return False
        
        # 执行删除
        success = dao.delete_reminder(reminder_id_to_delete)
        
        if success:
            print(f"\n✅ 成功删除提醒 {reminder_id_to_delete}")
            return True
        else:
            print(f"\n❌ 删除提醒失败")
            return False
        
    except Exception as e:
        print(f"删除过程中出现错误: {e}")
        return False
    finally:
        dao.close()


def main():
    print("=" * 60)
    print("              删除特定重复提醒工具")
    print("=" * 60)
    print("此工具将删除以下重复提醒:")
    print("用户 69460cdbf09e7d5a55ad9f94")
    print("时间: 星期六晚上11点4分")
    print("标题: 站起来活动一下")
    print("删除单次类型的提醒，保留interval类型的提醒")
    print()
    
    remove_specific_duplicate()


if __name__ == "__main__":
    main()