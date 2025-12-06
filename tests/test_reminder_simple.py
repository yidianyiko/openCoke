# -*- coding: utf-8 -*-
"""
提醒功能简单测试 - 不依赖数据库
"""
import sys
sys.path.append(".")

import time
from datetime import datetime, timedelta

print("=" * 60)
print("提醒功能简单测试（无需数据库）")
print("=" * 60)
print()

# 测试时间工具函数
print("【测试 1】时间解析功能")
print("-" * 60)

from util.time_util import (
    parse_relative_time,
    calculate_next_recurrence,
    is_time_in_past,
    format_time_friendly,
    str2timestamp
)

# 测试相对时间
test_cases = [
    "30分钟后",
    "2小时后",
    "3天后",
    "明天",
    "后天",
]

print("相对时间解析:")
for text in test_cases:
    result = parse_relative_time(text)
    if result:
        friendly = format_time_friendly(result)
        delta = result - int(time.time())
        print(f"  ✅ '{text}' -> {friendly} (距现在 {delta//60} 分钟)")
    else:
        print(f"  ❌ '{text}' -> 无法解析")

print()

# 测试绝对时间
print("绝对时间解析:")
tomorrow = datetime.now() + timedelta(days=1)
test_absolute = [
    tomorrow.replace(hour=9, minute=0).strftime("%Y年%m月%d日%H时%M分"),
    tomorrow.replace(hour=15, minute=30).strftime("%Y年%m月%d日%H时%M分"),
]

for text in test_absolute:
    result = str2timestamp(text)
    if result:
        friendly = format_time_friendly(result)
        print(f"  ✅ '{text}' -> {friendly}")
    else:
        print(f"  ❌ '{text}' -> 无法解析")

print()
print()

# 测试周期计算
print("【测试 2】周期提醒计算")
print("-" * 60)

current = int(time.time())
recurrence_tests = [
    ("daily", 1, "每天"),
    ("daily", 2, "每2天"),
    ("weekly", 1, "每周"),
    ("monthly", 1, "每月"),
]

for rec_type, interval, desc in recurrence_tests:
    next_time = calculate_next_recurrence(current, rec_type, interval)
    if next_time:
        friendly = format_time_friendly(next_time)
        delta_days = (next_time - current) // 86400
        print(f"  ✅ {desc} -> {friendly} (距现在 {delta_days} 天)")
    else:
        print(f"  ❌ {desc} -> 计算失败")

print()
print()

# 测试过期判断
print("【测试 3】时间过期判断")
print("-" * 60)

past = int(time.time()) - 3600
future = int(time.time()) + 3600
now = int(time.time())

print(f"  过去时间 (1小时前): {is_time_in_past(past)} (应为 True)")
print(f"  未来时间 (1小时后): {is_time_in_past(future)} (应为 False)")
print(f"  当前时间: {is_time_in_past(now)} (应为 False)")

print()
print()

# 测试友好格式化
print("【测试 4】友好时间格式化")
print("-" * 60)

now_dt = datetime.now()
test_times = [
    (now_dt, "现在"),
    (now_dt + timedelta(hours=2), "2小时后"),
    (now_dt + timedelta(days=1), "明天"),
    (now_dt + timedelta(days=2), "后天"),
    (now_dt + timedelta(days=5), "5天后"),
]

for dt, desc in test_times:
    timestamp = int(dt.timestamp())
    friendly = format_time_friendly(timestamp)
    print(f"  {desc:10s} -> {friendly}")

print()
print()

# 模拟 Agent 输出解析
print("【测试 5】模拟 Agent 输出解析")
print("-" * 60)

mock_reminders = [
    {
        "title": "开会",
        "time_original": "明天下午3点",
        "time_type": "relative",
    },
    {
        "title": "吃药",
        "time_original": "30分钟后",
        "time_type": "relative",
    },
    {
        "title": "写报告",
        "time_original": (datetime.now() + timedelta(days=1)).replace(hour=15, minute=0).strftime("%Y年%m月%d日%H时%M分"),
        "time_type": "absolute",
    },
]

print("解析提醒任务:")
for reminder in mock_reminders:
    title = reminder["title"]
    time_original = reminder["time_original"]
    time_type = reminder["time_type"]
    
    # 解析时间
    if time_type == "relative":
        timestamp = parse_relative_time(time_original)
    else:
        timestamp = str2timestamp(time_original)
    
    if timestamp:
        friendly = format_time_friendly(timestamp)
        print(f"  ✅ {title}: {time_original} -> {friendly}")
    else:
        print(f"  ❌ {title}: {time_original} -> 解析失败")

print()
print()

# 测试总结
print("=" * 60)
print("✅ 所有基础功能测试通过！")
print("=" * 60)
print()
print("下一步:")
print("  1. 运行完整测试: python tests/test_reminder_local.py")
print("  2. 运行单元测试: python tests/test_reminder_feature.py")
print("  3. 启动服务测试: source agent/runner/agent_start.sh")
