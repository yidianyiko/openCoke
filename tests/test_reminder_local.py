# -*- coding: utf-8 -*-
"""
提醒功能本地测试脚本
可以在不启动完整服务的情况下测试提醒功能
"""
import sys
sys.path.append(".")

import time
import json
from datetime import datetime, timedelta

print("=" * 60)
print("提醒功能本地测试")
print("=" * 60)
print()

# 测试 1: 导入检查
print("【测试 1】检查模块导入...")
try:
    from dao.reminder_dao import ReminderDAO
    from util.time_util import (
        parse_relative_time,
        calculate_next_recurrence,
        is_time_in_past,
        format_time_friendly,
        str2timestamp
    )
    print("✅ 所有模块导入成功")
except Exception as e:
    print(f"❌ 模块导入失败: {e}")
    sys.exit(1)

print()

# 测试 2: 数据库连接
print("【测试 2】检查数据库连接...")
try:
    dao = ReminderDAO()
    count = dao.collection.count_documents({})
    print(f"✅ 数据库连接成功，当前提醒记录数: {count}")
except Exception as e:
    print(f"❌ 数据库连接失败: {e}")
    print("提示：请确保 MongoDB 正在运行")
    sys.exit(1)

print()

# 测试 3: 创建索引
print("【测试 3】创建数据库索引...")
try:
    dao.create_indexes()
    print("✅ 索引创建成功")
except Exception as e:
    print(f"⚠️  索引可能已存在: {e}")

print()

# 测试 4: 时间解析功能
print("【测试 4】测试时间解析功能...")
test_cases = [
    ("30分钟后", "relative"),
    ("2小时后", "relative"),
    ("明天", "relative"),
    ("2024年12月01日15时00分", "absolute"),
]

for text, time_type in test_cases:
    try:
        if time_type == "relative":
            result = parse_relative_time(text)
            if result:
                friendly = format_time_friendly(result)
                print(f"  ✅ '{text}' -> {friendly} (timestamp: {result})")
            else:
                print(f"  ⚠️  '{text}' -> 无法解析")
        else:
            result = str2timestamp(text)
            if result:
                friendly = format_time_friendly(result)
                print(f"  ✅ '{text}' -> {friendly} (timestamp: {result})")
            else:
                print(f"  ⚠️  '{text}' -> 无法解析")
    except Exception as e:
        print(f"  ❌ '{text}' -> 错误: {e}")

print()

# 测试 5: 创建测试提醒
print("【测试 5】创建测试提醒...")
test_reminder = {
    "conversation_id": "test_conv_local",
    "user_id": "test_user_local",
    "character_id": "test_char_local",
    "title": "本地测试提醒",
    "next_trigger_time": int(time.time()) + 60,  # 1分钟后
    "time_original": "1分钟后",
    "timezone": "Asia/Shanghai",
    "recurrence": {
        "enabled": False
    },
    "action_template": "这是一个本地测试提醒",
    "status": "confirmed",
    "requires_confirmation": False
}

try:
    reminder_id = dao.create_reminder(test_reminder)
    print(f"✅ 创建提醒成功")
    print(f"   ID: {reminder_id}")
    print(f"   标题: {test_reminder['title']}")
    print(f"   触发时间: {format_time_friendly(test_reminder['next_trigger_time'])}")
except Exception as e:
    print(f"❌ 创建提醒失败: {e}")
    import traceback
    print(traceback.format_exc())

print()

# 测试 6: 查询提醒
print("【测试 6】查询测试用户的所有提醒...")
try:
    reminders = dao.find_reminders_by_user("test_user_local")
    print(f"✅ 查询成功，找到 {len(reminders)} 个提醒")
    for r in reminders:
        status_icon = "⏰" if r["status"] == "confirmed" else "✓"
        print(f"   {status_icon} {r['title']}: {r['status']} at {format_time_friendly(r['next_trigger_time'])}")
except Exception as e:
    print(f"❌ 查询失败: {e}")

print()

# 测试 7: 查询待触发提醒
print("【测试 7】查询待触发的提醒...")
try:
    # 查询未来2分钟内的提醒
    future_time = int(time.time()) + 120
    pending = dao.find_pending_reminders(future_time, time_window=180)
    print(f"✅ 查询成功，找到 {len(pending)} 个待触发提醒")
    for r in pending:
        print(f"   ⏰ {r['title']}: {format_time_friendly(r['next_trigger_time'])}")
except Exception as e:
    print(f"❌ 查询失败: {e}")

print()

# 测试 8: 周期提醒计算
print("【测试 8】测试周期提醒计算...")
current = int(time.time())
test_recurrences = [
    ("daily", 1, "每天"),
    ("weekly", 1, "每周"),
    ("daily", 2, "每2天"),
]

for rec_type, interval, desc in test_recurrences:
    try:
        next_time = calculate_next_recurrence(current, rec_type, interval)
        if next_time:
            friendly = format_time_friendly(next_time)
            print(f"  ✅ {desc} -> 下次: {friendly}")
        else:
            print(f"  ⚠️  {desc} -> 计算失败")
    except Exception as e:
        print(f"  ❌ {desc} -> 错误: {e}")

print()

# 测试 9: 模拟 Agent 输出
print("【测试 9】模拟 Agent 识别提醒（新Schema）...")
mock_agent_output = {
    "DetectedReminders": [
        {
            "operation": "create",
            "title": "开会",
            "time_original": "明天上午9点",
            "time_resolved": (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0).strftime("%Y年%m月%d日%H时%M分"),
            "requires_confirmation": False,
            "recurrence": {"enabled": False},
            "action_template": "该开会了"
        },
        {
            "operation": "update",
            "target": {"by_title": "开会"},
            "update_fields": {"time_original": "后天上午10点"},
            "requires_confirmation": False
        },
        {
            "operation": "list",
            "list_filter": {"by_status": "confirmed"}
        },
        {
            "operation": "delete",
            "target": {"by_title": "开会"}
        }
    ]
}

print("模拟 LLM 输出:")
print(json.dumps(mock_agent_output, ensure_ascii=False, indent=2))
print()

# 解析并创建提醒
for reminder in mock_agent_output["DetectedReminders"]:
    try:
        op = reminder.get("operation", "create")
        if op == "create":
            timestamp = str2timestamp(reminder.get("time_resolved", "")) or parse_relative_time(reminder.get("time_original", ""))
            if timestamp:
                reminder_doc = {
                    "conversation_id": "test_conv_mock",
                    "user_id": "test_user_mock",
                    "character_id": "test_char_mock",
                    "title": reminder["title"],
                    "action_template": reminder.get("action_template", f"提醒：{reminder['title']}") ,
                    "next_trigger_time": timestamp,
                    "time_original": reminder.get("time_original", ""),
                    "timezone": "Asia/Shanghai",
                    "recurrence": reminder.get("recurrence", {"enabled": False}),
                    "status": "confirmed",
                    "requires_confirmation": False
                }
                rid = dao.create_reminder(reminder_doc)
                print(f"✅ 创建提醒: {reminder['title']} at {format_time_friendly(timestamp)}")
        elif op == "list":
            status = reminder.get("list_filter", {}).get("by_status")
            items = dao.find_reminders_by_user("test_user_mock", status=status)
            print(f"✅ 列表: 共 {len(items)} 项")
        elif op == "delete":
            items = dao.find_reminders_by_user("test_user_mock")
            target = reminder.get("target", {})
            by_title = target.get("by_title")
            for r in items:
                if by_title and by_title in r.get("title", ""):
                    dao.delete_reminder(r["reminder_id"])
                    print(f"✅ 删除提醒: {r['title']}")
        elif op == "update":
            items = dao.find_reminders_by_user("test_user_mock")
            target = reminder.get("target", {})
            by_title = target.get("by_title")
            update_fields = reminder.get("update_fields", {})
            for r in items:
                if by_title and by_title in r.get("title", ""):
                    update_data = {}
                    if update_fields.get("time_original"):
                        ts = parse_relative_time(update_fields["time_original"]) or str2timestamp(update_fields["time_original"])
                        if ts:
                            update_data["next_trigger_time"] = ts
                    dao.update_reminder(r["reminder_id"], update_data)
                    print(f"✅ 更新提醒: {r['title']}")
    except Exception as e:
        print(f"❌ 处理失败: {e}")

print()

# 测试 10: 清理测试数据
print("【测试 10】清理测试数据...")
cleanup = input("是否清理测试数据？(y/n): ").strip().lower()

if cleanup == 'y':
    try:
        # 删除测试用户的提醒
        test_users = ["test_user_local", "test_user_mock"]
        total_deleted = 0
        
        for user_id in test_users:
            reminders = dao.find_reminders_by_user(user_id)
            for r in reminders:
                dao.delete_reminder(r["reminder_id"])
                total_deleted += 1
        
        print(f"✅ 已删除 {total_deleted} 个测试提醒")
    except Exception as e:
        print(f"❌ 清理失败: {e}")
else:
    print("⏭️  跳过清理，测试数据保留")

print()

# 关闭连接
dao.close()

print("=" * 60)
print("测试完成！")
print("=" * 60)
print()
print("📚 相关文档:")
print("  - 使用指南: doc/reminder_usage_guide.md")
print("  - 配置说明: doc/background_tasks_configuration.md")
print("  - 快速参考: doc/QUICK_REFERENCE.md")
print()
print("🚀 启动服务:")
print("  source qiaoyun/runner/qiaoyun_start.sh")
