# -*- coding: utf-8 -*-
"""
用户指标分析脚本 (详细版)

包含以下分析：
1. 成本分析：日均交互次数、LLM调用估算、成本估算、月度预测
2. Cohort留存分析：按注册周分组，计算 Day1/3/5/7/14/30 留存率
3. 用户分层分析：日均交互分布、Pareto分析、百分位数分析
4. 每日活跃趋势：最近30天的日活跃用户数和交互量
5. 用户生命周期：按活跃天数分布、用户状态分析
6. CSV导出：user_summary.csv 和 daily_activity.csv

Usage:
    python scripts/analyze_user_metrics.py          # 完整报告
    python scripts/analyze_user_metrics.py --cost   # 成本分析
    python scripts/analyze_user_metrics.py --cohort # 留存分析
    python scripts/analyze_user_metrics.py --distribution # 分层分析
    python scripts/analyze_user_metrics.py --trend  # 趋势分析
    python scripts/analyze_user_metrics.py --export-csv  # 导出CSV
    python scripts/analyze_user_metrics.py --export-csv --output-dir ./output  # 指定输出目录
"""
import sys

sys.path.append(".")

import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics

from bson import ObjectId

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)

# ============================================================
# 常量配置
# ============================================================
LLM_CALL_MULTIPLIER = 3.5  # 1次用户交互 ≈ 3.5次 LLM 调用
ESTIMATED_TOKENS_PER_CALL = 1000  # 每次 LLM 调用估算 token 数
COST_PER_MILLION_TOKENS = 0.50  # 每百万 token 费用（美元）
DAYS_FOR_TREND = 30  # 趋势分析天数


# ============================================================
# 工具函数
# ============================================================
def format_timestamp(timestamp: Optional[float]) -> str:
    """将时间戳格式化为可读日期"""
    if not timestamp:
        return "N/A"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, TypeError):
        return str(timestamp)


def format_date(timestamp: Optional[float]) -> str:
    """将时间戳格式化为日期（不含时间）"""
    if not timestamp:
        return "N/A"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (ValueError, OSError, TypeError):
        return str(timestamp)


def get_user_creation_time(user_id: str) -> Optional[float]:
    """从用户ID的ObjectId中提取创建时间"""
    try:
        obj_id = ObjectId(user_id)
        return obj_id.generation_time.timestamp()
    except Exception:
        return None


def get_week_start(timestamp: float) -> datetime:
    """获取时间戳所在周的周一"""
    dt = datetime.fromtimestamp(timestamp)
    return dt - timedelta(days=dt.weekday())


def get_week_label(week_start: datetime) -> str:
    """获取周标签，如 '12月16-22日'"""
    week_end = week_start + timedelta(days=6)
    if week_start.month == week_end.month:
        return f"{week_start.month}月{week_start.day}-{week_end.day}日"
    else:
        return f"{week_start.month}月{week_start.day}日-{week_end.month}月{week_end.day}日"


# ============================================================
# 数据获取函数
# ============================================================
def get_user_input_messages(mongo_db: MongoDBBase, user_id: str) -> List[Dict]:
    """获取用户的所有输入消息"""
    return mongo_db.find_many("inputmessages", {"from_user": user_id})


def get_user_message_dates(mongo_db: MongoDBBase, user_id: str) -> List[datetime]:
    """获取用户所有有消息的日期"""
    messages = mongo_db.find_many("inputmessages", {"from_user": user_id})
    dates = set()
    for msg in messages:
        ts = msg.get("input_timestamp")
        if ts:
            try:
                dates.add(datetime.fromtimestamp(ts).date())
            except (ValueError, OSError, TypeError):
                pass
    return sorted(list(dates))


def get_user_first_message_time(mongo_db: MongoDBBase, user_id: str) -> Optional[float]:
    """获取用户第一条输入消息的时间"""
    try:
        cursor = (
            mongo_db.db["inputmessages"]
            .find({"from_user": user_id})
            .sort("input_timestamp", 1)
            .limit(1)
        )
        msgs = list(cursor)
        if msgs:
            return msgs[0].get("input_timestamp")
    except Exception:
        pass
    return None


def get_user_last_message_time(mongo_db: MongoDBBase, user_id: str) -> Optional[float]:
    """获取用户最后一条输入消息的时间"""
    try:
        cursor = (
            mongo_db.db["inputmessages"]
            .find({"from_user": user_id})
            .sort("input_timestamp", -1)
            .limit(1)
        )
        msgs = list(cursor)
        if msgs:
            return msgs[0].get("input_timestamp")
    except Exception:
        pass
    return None


def count_user_input_messages(mongo_db: MongoDBBase, user_id: str) -> int:
    """统计用户的输入消息数量"""
    return mongo_db.count_documents("inputmessages", {"from_user": user_id})


# ============================================================
# 分析函数
# ============================================================
def analyze_cost_metrics(users: List[Dict], mongo_db: MongoDBBase) -> Dict:
    """
    成本分析指标
    
    返回:
        - 总用户数
        - 总交互次数
        - 估算 LLM 调用次数
        - 估算 token 消耗
        - 估算成本
        - 每用户平均数据
    """
    import time
    current_time = time.time()
    
    total_interactions = 0
    user_stats = []
    
    for user in users:
        user_id = str(user.get("_id", ""))
        if not user_id:
            continue
            
        # 获取用户消息统计
        input_count = count_user_input_messages(mongo_db, user_id)
        first_msg_time = get_user_first_message_time(mongo_db, user_id)
        last_msg_time = get_user_last_message_time(mongo_db, user_id)
        
        # 计算活跃天数
        active_days = 1
        if first_msg_time and last_msg_time:
            active_days = max(1, (last_msg_time - first_msg_time) / 86400)
        
        # 日均交互次数
        daily_avg = input_count / active_days if active_days > 0 else 0
        
        total_interactions += input_count
        
        user_stats.append({
            "user_id": user_id,
            "name": user.get("name", "N/A"),
            "input_count": input_count,
            "active_days": active_days,
            "daily_avg": daily_avg,
            "first_msg_time": first_msg_time,
            "last_msg_time": last_msg_time,
        })
    
    # 计算汇总数据
    total_users = len(users)
    total_llm_calls = total_interactions * LLM_CALL_MULTIPLIER
    total_tokens = total_llm_calls * ESTIMATED_TOKENS_PER_CALL
    total_cost = (total_tokens / 1_000_000) * COST_PER_MILLION_TOKENS
    
    # 过滤活跃用户（有交互的用户）
    active_users = [u for u in user_stats if u["input_count"] > 0]
    avg_interactions_per_user = total_interactions / len(active_users) if active_users else 0
    avg_daily_per_user = sum(u["daily_avg"] for u in active_users) / len(active_users) if active_users else 0
    
    return {
        "total_users": total_users,
        "active_users": len(active_users),
        "total_interactions": total_interactions,
        "total_llm_calls": total_llm_calls,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "avg_interactions_per_user": avg_interactions_per_user,
        "avg_daily_per_user": avg_daily_per_user,
        "user_stats": sorted(user_stats, key=lambda x: x["input_count"], reverse=True),
    }


def analyze_cohort_retention(users: List[Dict], mongo_db: MongoDBBase) -> Dict:
    """
    Cohort 留存分析（按注册周分组）
    
    计算每个 Cohort 的 Day1/3/5/7/14/30 留存率
    活跃定义：当天有 ≥1 条 inputmessage
    """
    import time
    current_time = time.time()
    today = datetime.now().date()
    
    # 按注册周分组用户
    cohorts = defaultdict(list)
    
    # 留存天数配置
    retention_days = [1, 3, 5, 7, 14, 30]
    
    for user in users:
        user_id = str(user.get("_id", ""))
        creation_time = get_user_creation_time(user_id)
        
        if not creation_time:
            continue
        
        week_start = get_week_start(creation_time)
        week_start_date = week_start.date()
        
        # 获取用户所有活跃日期
        active_dates = get_user_message_dates(mongo_db, user_id)
        registration_date = datetime.fromtimestamp(creation_time).date()
        
        cohorts[week_start_date].append({
            "user_id": user_id,
            "registration_date": registration_date,
            "active_dates": set(active_dates),
            "total_active_days": len(active_dates),
        })
    
    # 计算每个 Cohort 的留存率
    cohort_results = []
    
    for week_start_date in sorted(cohorts.keys(), reverse=True):
        cohort_users = cohorts[week_start_date]
        cohort_size = len(cohort_users)
        
        if cohort_size == 0:
            continue
        
        # 检查是否有足够的时间来计算留存
        days_since_cohort = (today - week_start_date).days
        
        # 初始化留存数据
        retention = {}
        retention_rates = {}
        retention_possible = {}
        
        for day in retention_days:
            day_key = f"day{day}"
            retention[day_key] = 0
            retention_possible[day_key] = days_since_cohort >= day
        
        # 计算累积留存（第N天及之后是否有活跃）
        cumulative_retention = {}
        for day in retention_days:
            cumulative_retention[f"day{day}"] = 0
        
        # 统计每个用户的活跃天数
        total_active_days_in_cohort = 0
        
        for user_data in cohort_users:
            reg_date = user_data["registration_date"]
            active_dates = user_data["active_dates"]
            total_active_days_in_cohort += user_data["total_active_days"]
            
            for day in retention_days:
                day_key = f"day{day}"
                target_date = reg_date + timedelta(days=day)
                
                # 精确留存：第N天是否活跃
                if target_date in active_dates:
                    retention[day_key] += 1
                
                # 累积留存：第N天及之后是否有任何活跃
                has_activity_after = any(
                    d >= target_date for d in active_dates
                )
                if has_activity_after:
                    cumulative_retention[day_key] += 1
        
        # 计算留存率
        for day in retention_days:
            day_key = f"day{day}"
            if retention_possible[day_key]:
                retention_rates[day_key] = (retention[day_key] / cohort_size) * 100
            else:
                retention_rates[day_key] = None
        
        # 计算累积留存率
        cumulative_rates = {}
        for day in retention_days:
            day_key = f"day{day}"
            if retention_possible[day_key]:
                cumulative_rates[day_key] = (cumulative_retention[day_key] / cohort_size) * 100
            else:
                cumulative_rates[day_key] = None
        
        avg_active_days = total_active_days_in_cohort / cohort_size if cohort_size > 0 else 0
        
        cohort_results.append({
            "week_start": week_start_date,
            "week_label": get_week_label(datetime.combine(week_start_date, datetime.min.time())),
            "cohort_size": cohort_size,
            "retention": retention,
            "retention_rates": retention_rates,
            "cumulative_retention": cumulative_retention,
            "cumulative_rates": cumulative_rates,
            "avg_active_days": avg_active_days,
        })
    
    return {
        "cohorts": cohort_results,
        "retention_days": retention_days,
    }


def analyze_user_distribution(users: List[Dict], mongo_db: MongoDBBase) -> Dict:
    """
    用户分层分析
    
    - 日均交互分布
    - Pareto 分析（Top 20% 用户贡献多少交互）
    - 百分位数分析
    - 活跃天数分布
    """
    user_data_list = []
    user_daily_avgs = []
    user_totals = []
    user_active_days = []
    
    for user in users:
        user_id = str(user.get("_id", ""))
        if not user_id:
            continue
        
        input_count = count_user_input_messages(mongo_db, user_id)
        first_msg_time = get_user_first_message_time(mongo_db, user_id)
        last_msg_time = get_user_last_message_time(mongo_db, user_id)
        active_dates = get_user_message_dates(mongo_db, user_id)
        
        if input_count == 0:
            continue
        
        # 计算活跃天数（实际有消息的天数）
        actual_active_days = len(active_dates)
        
        # 计算生命周期天数
        lifecycle_days = 1
        if first_msg_time and last_msg_time:
            lifecycle_days = max(1, (last_msg_time - first_msg_time) / 86400)
        
        daily_avg = input_count / lifecycle_days
        
        user_data_list.append({
            "user_id": user_id,
            "input_count": input_count,
            "actual_active_days": actual_active_days,
            "lifecycle_days": lifecycle_days,
            "daily_avg": daily_avg,
        })
        
        user_daily_avgs.append(daily_avg)
        user_totals.append(input_count)
        user_active_days.append(actual_active_days)
    
    if not user_totals:
        return {"distribution": [], "pareto": {}, "percentiles": {}, "active_days_distribution": []}
    
    # 日均交互分布（分桶）
    buckets = [
        (0, 1, "0-1"),
        (1, 2, "1-2"),
        (2, 5, "2-5"),
        (5, 10, "5-10"),
        (10, 20, "10-20"),
        (20, 50, "20-50"),
        (50, 100, "50-100"),
        (100, float("inf"), "100+"),
    ]
    
    distribution = []
    for low, high, label in buckets:
        count = sum(1 for avg in user_daily_avgs if low <= avg < high)
        if count > 0:  # 只显示有数据的桶
            distribution.append({"range": label, "count": count})
    
    # 活跃天数分布
    active_days_buckets = [
        (1, 1, "1天"),
        (2, 3, "2-3天"),
        (4, 7, "4-7天"),
        (8, 14, "8-14天"),
        (15, 30, "15-30天"),
        (31, float("inf"), "30天+"),
    ]
    
    active_days_distribution = []
    for low, high, label in active_days_buckets:
        count = sum(1 for days in user_active_days if low <= days <= high)
        if count > 0:
            active_days_distribution.append({"range": label, "count": count})
    
    # Pareto 分析（更详细）
    sorted_totals = sorted(user_totals, reverse=True)
    total_sum = sum(sorted_totals)
    
    pareto = {
        "total_active_users": len(user_totals),
        "total_interactions": total_sum,
    }
    
    if total_sum > 0:
        for pct in [1, 5, 10, 20, 50]:
            top_count = max(1, len(sorted_totals) * pct // 100)
            top_sum = sum(sorted_totals[:top_count])
            pareto[f"top_{pct}_users"] = top_count
            pareto[f"top_{pct}_interactions"] = top_sum
            pareto[f"top_{pct}_percentage"] = (top_sum / total_sum) * 100
    
    # 百分位数分析
    sorted_daily_avgs = sorted(user_daily_avgs)
    percentiles = {}
    for p in [10, 25, 50, 75, 90, 95, 99]:
        idx = int(len(sorted_daily_avgs) * p / 100)
        idx = min(idx, len(sorted_daily_avgs) - 1)
        percentiles[f"p{p}"] = sorted_daily_avgs[idx]
    
    # 统计数据
    daily_avg_stats = {
        "min": min(user_daily_avgs),
        "max": max(user_daily_avgs),
        "avg": statistics.mean(user_daily_avgs),
        "median": statistics.median(user_daily_avgs),
        "stdev": statistics.stdev(user_daily_avgs) if len(user_daily_avgs) > 1 else 0,
    }
    
    active_days_stats = {
        "min": min(user_active_days),
        "max": max(user_active_days),
        "avg": statistics.mean(user_active_days),
        "median": statistics.median(user_active_days),
    }
    
    # 用户分层定义（基于日均交互）
    tiers = {
        "light": sum(1 for avg in user_daily_avgs if avg < 5),
        "medium": sum(1 for avg in user_daily_avgs if 5 <= avg < 20),
        "heavy": sum(1 for avg in user_daily_avgs if avg >= 20),
    }
    
    return {
        "distribution": distribution,
        "active_days_distribution": active_days_distribution,
        "pareto": pareto,
        "percentiles": percentiles,
        "daily_avg_stats": daily_avg_stats,
        "active_days_stats": active_days_stats,
        "tiers": tiers,
        "user_data": sorted(user_data_list, key=lambda x: x["input_count"], reverse=True),
    }


def analyze_daily_trend(users: List[Dict], mongo_db: MongoDBBase) -> Dict:
    """
    每日活跃趋势分析
    
    最近N天的日活跃用户数和交互量
    """
    today = datetime.now().date()
    
    # 统计每天的数据
    daily_stats = defaultdict(lambda: {"users": set(), "interactions": 0})
    
    for user in users:
        user_id = str(user.get("_id", ""))
        if not user_id:
            continue
        
        # 获取用户所有消息
        messages = mongo_db.find_many("inputmessages", {"from_user": user_id})
        
        for msg in messages:
            ts = msg.get("input_timestamp")
            if ts:
                try:
                    msg_date = datetime.fromtimestamp(ts).date()
                    days_ago = (today - msg_date).days
                    if 0 <= days_ago < DAYS_FOR_TREND:
                        daily_stats[msg_date]["users"].add(user_id)
                        daily_stats[msg_date]["interactions"] += 1
                except (ValueError, OSError, TypeError):
                    pass
    
    # 生成最近N天的数据
    trend_data = []
    for i in range(DAYS_FOR_TREND - 1, -1, -1):
        date = today - timedelta(days=i)
        stats = daily_stats.get(date, {"users": set(), "interactions": 0})
        trend_data.append({
            "date": date,
            "date_str": date.strftime("%m-%d"),
            "weekday": date.strftime("%a"),
            "dau": len(stats["users"]),
            "interactions": stats["interactions"],
        })
    
    # 计算汇总统计
    dau_values = [d["dau"] for d in trend_data if d["dau"] > 0]
    interaction_values = [d["interactions"] for d in trend_data if d["interactions"] > 0]
    
    summary = {
        "avg_dau": statistics.mean(dau_values) if dau_values else 0,
        "max_dau": max(dau_values) if dau_values else 0,
        "min_dau": min(dau_values) if dau_values else 0,
        "avg_interactions": statistics.mean(interaction_values) if interaction_values else 0,
        "max_interactions": max(interaction_values) if interaction_values else 0,
    }
    
    return {
        "trend": trend_data,
        "summary": summary,
    }


# ============================================================
# 报告输出函数
# ============================================================
def print_cost_report(cost_data: Dict):
    """打印成本分析报告"""
    print("\n" + "=" * 80)
    print("成本分析报告")
    print("=" * 80)
    print(f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 80)
    
    print(f"\n【用户概览】")
    print(f"  总用户数: {cost_data['total_users']}")
    print(f"  活跃用户数（有交互）: {cost_data['active_users']}")
    
    print(f"\n【交互统计】")
    print(f"  总交互次数（inputmessages）: {cost_data['total_interactions']:,}")
    print(f"  平均每活跃用户交互次数: {cost_data['avg_interactions_per_user']:.2f}")
    print(f"  平均每用户日均交互: {cost_data['avg_daily_per_user']:.2f}")
    
    print(f"\n【LLM调用估算】（系数: {LLM_CALL_MULTIPLIER}）")
    print(f"  估算 LLM 调用次数: {cost_data['total_llm_calls']:,.0f}")
    print(f"  估算 Token 消耗: {cost_data['total_tokens']:,.0f}")
    print(f"  估算总成本: ${cost_data['total_cost']:.2f}")
    
    print(f"\n【用户明细 - Top 10】")
    print(f"{'用户ID':<26} {'用户名':<15} {'交互数':<10} {'活跃天数':<10} {'日均':<10}")
    print("-" * 80)
    
    for stat in cost_data["user_stats"][:10]:
        print(
            f"{stat['user_id'][:24]:<26} "
            f"{stat['name'][:13]:<15} "
            f"{stat['input_count']:<10} "
            f"{stat['active_days']:<10.1f} "
            f"{stat['daily_avg']:<10.2f}"
        )


def print_cohort_report(cohort_data: Dict):
    """打印 Cohort 留存报告"""
    print("\n" + "=" * 120)
    print("Cohort 留存分析报告")
    print("=" * 120)
    print("定义: 按注册周分组，计算各天留存率")
    print("活跃定义: 当天有 ≥1 条 inputmessage")
    print("-" * 120)
    
    # 精确留存表头
    print(f"\n【精确留存率】（第N天当天是否活跃）")
    print(f"{'注册周':<18} {'用户数':<8} {'Day1':<8} {'Day3':<8} {'Day5':<8} {'Day7':<8} {'Day14':<8} {'Day30':<8} {'平均活跃天数':<12}")
    print("-" * 120)
    
    for cohort in cohort_data["cohorts"]:
        rates = cohort['retention_rates']
        
        def fmt_rate(key):
            return f"{rates[key]:.1f}%" if rates.get(key) is not None else "-"
        
        print(
            f"{cohort['week_label']:<18} "
            f"{cohort['cohort_size']:<8} "
            f"{fmt_rate('day1'):<8} "
            f"{fmt_rate('day3'):<8} "
            f"{fmt_rate('day5'):<8} "
            f"{fmt_rate('day7'):<8} "
            f"{fmt_rate('day14'):<8} "
            f"{fmt_rate('day30'):<8} "
            f"{cohort['avg_active_days']:<12.1f}"
        )
    
    # 累积留存表
    print(f"\n【累积留存率】（第N天及之后是否有任何活跃）")
    print(f"{'注册周':<18} {'用户数':<8} {'Day1+':<10} {'Day3+':<10} {'Day7+':<10} {'Day14+':<10} {'Day30+':<10}")
    print("-" * 120)
    
    for cohort in cohort_data["cohorts"]:
        cum_rates = cohort.get('cumulative_rates', {})
        
        def fmt_cum(key):
            return f"{cum_rates[key]:.1f}%" if cum_rates.get(key) is not None else "-"
        
        print(
            f"{cohort['week_label']:<18} "
            f"{cohort['cohort_size']:<8} "
            f"{fmt_cum('day1'):<10} "
            f"{fmt_cum('day3'):<10} "
            f"{fmt_cum('day7'):<10} "
            f"{fmt_cum('day14'):<10} "
            f"{fmt_cum('day30'):<10}"
        )
    
    # 绝对数字表
    print(f"\n【留存绝对数字】")
    print(f"{'注册周':<18} {'用户数':<8} {'Day1':<10} {'Day3':<10} {'Day5':<10} {'Day7':<10} {'Day14':<10} {'Day30':<10}")
    print("-" * 120)
    
    for cohort in cohort_data["cohorts"]:
        ret = cohort['retention']
        print(
            f"{cohort['week_label']:<18} "
            f"{cohort['cohort_size']:<8} "
            f"{ret.get('day1', 0):<10} "
            f"{ret.get('day3', 0):<10} "
            f"{ret.get('day5', 0):<10} "
            f"{ret.get('day7', 0):<10} "
            f"{ret.get('day14', 0):<10} "
            f"{ret.get('day30', 0):<10}"
        )
    
    print("\n说明: '-' 表示数据不足（该cohort注册时间不够长）")


def print_distribution_report(dist_data: Dict):
    """打印用户分层报告"""
    print("\n" + "=" * 100)
    print("用户分层分析报告")
    print("=" * 100)
    
    # 用户分层概览
    tiers = dist_data.get("tiers", {})
    total_users = sum(tiers.values())
    print(f"\n【用户分层概览】")
    print(f"  轻度用户 (日均<5次):   {tiers.get('light', 0):>6} 人 ({tiers.get('light', 0)/total_users*100 if total_users else 0:>5.1f}%)")
    print(f"  中度用户 (日均5-20次): {tiers.get('medium', 0):>6} 人 ({tiers.get('medium', 0)/total_users*100 if total_users else 0:>5.1f}%)")
    print(f"  重度用户 (日均20+次):  {tiers.get('heavy', 0):>6} 人 ({tiers.get('heavy', 0)/total_users*100 if total_users else 0:>5.1f}%)")
    
    print(f"\n【日均交互次数分布】")
    print(f"{'范围':<15} {'用户数':<10} {'占比':<10} {'柱状图'}")
    print("-" * 70)
    
    total_dist_users = sum(d["count"] for d in dist_data["distribution"])
    max_count = max(d["count"] for d in dist_data["distribution"]) if dist_data["distribution"] else 1
    
    for d in dist_data["distribution"]:
        pct = (d["count"] / total_dist_users * 100) if total_dist_users > 0 else 0
        bar_len = int((d["count"] / max_count) * 30) if max_count > 0 else 0
        bar = "█" * bar_len
        print(f"{d['range']:<15} {d['count']:<10} {pct:>6.1f}%    {bar}")
    
    # 活跃天数分布
    if dist_data.get("active_days_distribution"):
        print(f"\n【活跃天数分布】")
        print(f"{'范围':<15} {'用户数':<10} {'占比':<10} {'柱状图'}")
        print("-" * 70)
        
        total_ad = sum(d["count"] for d in dist_data["active_days_distribution"])
        max_ad = max(d["count"] for d in dist_data["active_days_distribution"])
        
        for d in dist_data["active_days_distribution"]:
            pct = (d["count"] / total_ad * 100) if total_ad > 0 else 0
            bar_len = int((d["count"] / max_ad) * 30) if max_ad > 0 else 0
            bar = "█" * bar_len
            print(f"{d['range']:<15} {d['count']:<10} {pct:>6.1f}%    {bar}")
    
    # Pareto 分析（详细）
    print(f"\n【Pareto 分析 - 交互量集中度】")
    pareto = dist_data["pareto"]
    print(f"  总活跃用户: {pareto['total_active_users']}")
    print(f"  总交互次数: {pareto['total_interactions']:,}")
    print(f"  " + "-" * 50)
    
    for pct in [1, 5, 10, 20, 50]:
        users = pareto.get(f'top_{pct}_users', 0)
        interactions = pareto.get(f'top_{pct}_interactions', 0)
        percentage = pareto.get(f'top_{pct}_percentage', 0)
        print(f"  Top {pct:>2}% 用户 ({users:>3}人) 贡献交互: {interactions:>6,} ({percentage:>5.1f}%)")
    
    # 百分位数分析
    if dist_data.get("percentiles"):
        print(f"\n【日均交互百分位数】")
        percentiles = dist_data["percentiles"]
        print(f"  P10: {percentiles.get('p10', 0):>8.2f}  (10%用户日均低于此值)")
        print(f"  P25: {percentiles.get('p25', 0):>8.2f}  (25%用户日均低于此值)")
        print(f"  P50: {percentiles.get('p50', 0):>8.2f}  (中位数)")
        print(f"  P75: {percentiles.get('p75', 0):>8.2f}  (75%用户日均低于此值)")
        print(f"  P90: {percentiles.get('p90', 0):>8.2f}  (90%用户日均低于此值)")
        print(f"  P95: {percentiles.get('p95', 0):>8.2f}  (95%用户日均低于此值)")
        print(f"  P99: {percentiles.get('p99', 0):>8.2f}  (99%用户日均低于此值)")
    
    # 统计数据
    print(f"\n【日均交互统计】")
    stats = dist_data["daily_avg_stats"]
    print(f"  最小值: {stats['min']:>10.2f}")
    print(f"  最大值: {stats['max']:>10.2f}")
    print(f"  平均值: {stats['avg']:>10.2f}")
    print(f"  中位数: {stats['median']:>10.2f}")
    print(f"  标准差: {stats['stdev']:>10.2f}")
    
    # 活跃天数统计
    if dist_data.get("active_days_stats"):
        print(f"\n【活跃天数统计】")
        ad_stats = dist_data["active_days_stats"]
        print(f"  最小值: {ad_stats['min']:>10.1f} 天")
        print(f"  最大值: {ad_stats['max']:>10.1f} 天")
        print(f"  平均值: {ad_stats['avg']:>10.1f} 天")
        print(f"  中位数: {ad_stats['median']:>10.1f} 天")


def print_trend_report(trend_data: Dict):
    """打印每日趋势报告"""
    print("\n" + "=" * 100)
    print(f"每日活跃趋势报告（最近 {DAYS_FOR_TREND} 天）")
    print("=" * 100)
    
    # 汇总统计
    summary = trend_data["summary"]
    print(f"\n【汇总统计】")
    print(f"  平均 DAU: {summary['avg_dau']:.1f}")
    print(f"  最高 DAU: {summary['max_dau']}")
    print(f"  最低 DAU: {summary['min_dau']}")
    print(f"  日均交互: {summary['avg_interactions']:.1f}")
    print(f"  最高日交互: {summary['max_interactions']}")
    
    # 每日明细
    print(f"\n【每日明细】")
    print(f"{'日期':<12} {'星期':<6} {'DAU':<8} {'交互数':<10} {'DAU趋势':<40} {'交互趋势'}")
    print("-" * 100)
    
    trend = trend_data["trend"]
    max_dau = max(d["dau"] for d in trend) if trend else 1
    max_interactions = max(d["interactions"] for d in trend) if trend else 1
    
    for d in trend:
        dau_bar_len = int((d["dau"] / max_dau) * 20) if max_dau > 0 else 0
        int_bar_len = int((d["interactions"] / max_interactions) * 20) if max_interactions > 0 else 0
        dau_bar = "█" * dau_bar_len
        int_bar = "█" * int_bar_len
        
        print(
            f"{d['date_str']:<12} "
            f"{d['weekday']:<6} "
            f"{d['dau']:<8} "
            f"{d['interactions']:<10} "
            f"{dau_bar:<40} "
            f"{int_bar}"
        )


# ============================================================
# CSV 导出函数
# ============================================================
def export_user_summary_csv(users: List[Dict], mongo_db: MongoDBBase, output_path: str):
    """
    导出用户汇总表 (user_summary.csv)
    
    字段说明：
    - user_id: 用户ID
    - name: 用户名称
    - is_character: 是否为角色用户
    - status: 用户状态 (normal/stopped)
    - registration_date: 注册日期 (从 ObjectId 提取)
    - platform_wechat_id: 微信统一ID
    - platform_wechat_account: 微信号
    - platform_wechat_nickname: 微信昵称
    - user_info_description_len: 用户描述长度
    - total_input_messages: 输入消息总数
    - total_output_messages: 输出消息总数
    - first_active_date: 首次活跃日期
    - last_active_date: 最后活跃日期
    - total_active_days: 总活跃天数
    - text_message_count: 文本消息数
    - voice_message_count: 语音消息数
    - image_message_count: 图片消息数
    - other_message_count: 其他消息数
    - avg_handle_time_seconds: 平均处理时间(秒)
    - relation_closeness: 关系亲密度
    - relation_trustness: 关系信任度
    - relation_dislike: 关系反感度
    - relation_description_len: 关系描述长度
    - conversation_proactive_times: 主动对话次数
    - has_future_action: 是否有未来行动规划
    """
    fieldnames = [
        "user_id",
        "name",
        "is_character",
        "status",
        "registration_date",
        "platform_wechat_id",
        "platform_wechat_account",
        "platform_wechat_nickname",
        "user_info_description_len",
        "total_input_messages",
        "total_output_messages",
        "first_active_date",
        "last_active_date",
        "total_active_days",
        "text_message_count",
        "voice_message_count",
        "image_message_count",
        "other_message_count",
        "avg_handle_time_seconds",
        "relation_closeness",
        "relation_trustness",
        "relation_dislike",
        "relation_description_len",
        "conversation_proactive_times",
        "has_future_action",
    ]
    
    rows = []
    for user in users:
        user_id = str(user.get("_id", ""))
        if not user_id:
            continue
        
        # 基本信息
        name = user.get("name", "")
        is_character = user.get("is_character", False)
        status = user.get("status", "")
        
        # 注册日期
        reg_time = get_user_creation_time(user_id)
        registration_date = format_date(reg_time) if reg_time else ""
        
        # 平台信息
        platforms = user.get("platforms", {})
        wechat = platforms.get("wechat", {})
        platform_wechat_id = wechat.get("id", "")
        platform_wechat_account = wechat.get("account", "")
        platform_wechat_nickname = wechat.get("nickname", "")
        
        # 用户信息
        user_info = user.get("user_info", {})
        user_info_desc = user_info.get("description", "") if user_info else ""
        user_info_description_len = len(user_info_desc) if user_info_desc else 0
        
        # 消息统计
        input_messages = mongo_db.find_many("inputmessages", {"from_user": user_id})
        output_messages = mongo_db.find_many("outputmessages", {"to_user": user_id})
        
        total_input = len(input_messages)
        total_output = len(output_messages)
        
        # 消息类型统计
        text_count = 0
        voice_count = 0
        image_count = 0
        other_count = 0
        handle_times = []
        active_dates = set()
        first_msg_time = None
        last_msg_time = None
        
        for msg in input_messages:
            msg_type = msg.get("message_type", "")
            if msg_type == "text":
                text_count += 1
            elif msg_type == "voice":
                voice_count += 1
            elif msg_type == "image":
                image_count += 1
            else:
                other_count += 1
            
            # 处理时间
            input_ts = msg.get("input_timestamp")
            handled_ts = msg.get("handled_timestamp")
            if input_ts and handled_ts:
                handle_times.append(handled_ts - input_ts)
            
            # 活跃日期
            if input_ts:
                try:
                    active_dates.add(datetime.fromtimestamp(input_ts).date())
                    if first_msg_time is None or input_ts < first_msg_time:
                        first_msg_time = input_ts
                    if last_msg_time is None or input_ts > last_msg_time:
                        last_msg_time = input_ts
                except (ValueError, OSError, TypeError):
                    pass
        
        first_active_date = format_date(first_msg_time) if first_msg_time else ""
        last_active_date = format_date(last_msg_time) if last_msg_time else ""
        total_active_days = len(active_dates)
        avg_handle_time = statistics.mean(handle_times) if handle_times else 0
        
        # 关系信息
        relation = mongo_db.find_one("relations", {"uid": user_id})
        rel_closeness = ""
        rel_trustness = ""
        rel_dislike = ""
        rel_desc_len = 0
        if relation:
            relationship = relation.get("relationship", {})
            rel_closeness = relationship.get("closeness", "")
            rel_trustness = relationship.get("trustness", "")
            rel_dislike = relationship.get("dislike", "")
            rel_desc = relationship.get("description", "")
            rel_desc_len = len(rel_desc) if rel_desc else 0
        
        # 会话信息
        conversation = mongo_db.find_one("conversations", {
            "talkers.id": user_id
        })
        proactive_times = 0
        has_future = False
        if conversation:
            conv_info = conversation.get("conversation_info", {})
            future = conv_info.get("future", {})
            if future:
                proactive_times = future.get("proactive_times", 0)
                has_future = bool(future.get("action"))
        
        rows.append({
            "user_id": user_id,
            "name": name,
            "is_character": is_character,
            "status": status,
            "registration_date": registration_date,
            "platform_wechat_id": platform_wechat_id,
            "platform_wechat_account": platform_wechat_account,
            "platform_wechat_nickname": platform_wechat_nickname,
            "user_info_description_len": user_info_description_len,
            "total_input_messages": total_input,
            "total_output_messages": total_output,
            "first_active_date": first_active_date,
            "last_active_date": last_active_date,
            "total_active_days": total_active_days,
            "text_message_count": text_count,
            "voice_message_count": voice_count,
            "image_message_count": image_count,
            "other_message_count": other_count,
            "avg_handle_time_seconds": round(avg_handle_time, 2),
            "relation_closeness": rel_closeness,
            "relation_trustness": rel_trustness,
            "relation_dislike": rel_dislike,
            "relation_description_len": rel_desc_len,
            "conversation_proactive_times": proactive_times,
            "has_future_action": has_future,
        })
    
    # 写入 CSV
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    return len(rows)


def export_daily_activity_csv(users: List[Dict], mongo_db: MongoDBBase, output_path: str):
    """
    导出每日活跃明细表 (daily_activity.csv)
    
    字段说明：
    - user_id: 用户ID
    - user_name: 用户名称
    - date: 日期
    - input_count: 当日输入消息数
    - output_count: 当日输出消息数
    - text_count: 文本消息数
    - voice_count: 语音消息数
    - image_count: 图片消息数
    - other_count: 其他消息数
    - first_message_hour: 当日首条消息小时
    - last_message_hour: 当日末条消息小时
    - avg_handle_time_seconds: 平均处理时间(秒)
    - pending_count: 待处理消息数
    - handled_count: 已处理消息数
    - failed_count: 处理失败消息数
    - canceled_count: 取消消息数
    """
    fieldnames = [
        "user_id",
        "user_name",
        "date",
        "input_count",
        "output_count",
        "text_count",
        "voice_count",
        "image_count",
        "other_count",
        "first_message_hour",
        "last_message_hour",
        "avg_handle_time_seconds",
        "pending_count",
        "handled_count",
        "failed_count",
        "canceled_count",
    ]
    
    rows = []
    for user in users:
        user_id = str(user.get("_id", ""))
        user_name = user.get("name", "")
        if not user_id:
            continue
        
        # 按日期分组的消息统计
        daily_stats = defaultdict(lambda: {
            "input_count": 0,
            "output_count": 0,
            "text_count": 0,
            "voice_count": 0,
            "image_count": 0,
            "other_count": 0,
            "first_msg_time": None,
            "last_msg_time": None,
            "handle_times": [],
            "pending_count": 0,
            "handled_count": 0,
            "failed_count": 0,
            "canceled_count": 0,
        })
        
        # 获取输入消息
        input_messages = mongo_db.find_many("inputmessages", {"from_user": user_id})
        for msg in input_messages:
            input_ts = msg.get("input_timestamp")
            if not input_ts:
                continue
            
            try:
                dt = datetime.fromtimestamp(input_ts)
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, OSError, TypeError):
                continue
            
            stats = daily_stats[date_str]
            stats["input_count"] += 1
            
            # 消息类型
            msg_type = msg.get("message_type", "")
            if msg_type == "text":
                stats["text_count"] += 1
            elif msg_type == "voice":
                stats["voice_count"] += 1
            elif msg_type == "image":
                stats["image_count"] += 1
            else:
                stats["other_count"] += 1
            
            # 消息状态
            status = msg.get("status", "")
            if status == "pending":
                stats["pending_count"] += 1
            elif status == "handled":
                stats["handled_count"] += 1
            elif status == "failed":
                stats["failed_count"] += 1
            elif status == "canceled":
                stats["canceled_count"] += 1
            
            # 时间范围
            if stats["first_msg_time"] is None or input_ts < stats["first_msg_time"]:
                stats["first_msg_time"] = input_ts
            if stats["last_msg_time"] is None or input_ts > stats["last_msg_time"]:
                stats["last_msg_time"] = input_ts
            
            # 处理时间
            handled_ts = msg.get("handled_timestamp")
            if handled_ts and input_ts:
                stats["handle_times"].append(handled_ts - input_ts)
        
        # 获取输出消息
        output_messages = mongo_db.find_many("outputmessages", {"to_user": user_id})
        for msg in output_messages:
            output_ts = msg.get("expect_output_timestamp") or msg.get("handled_timestamp")
            if not output_ts:
                continue
            
            try:
                dt = datetime.fromtimestamp(output_ts)
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, OSError, TypeError):
                continue
            
            daily_stats[date_str]["output_count"] += 1
        
        # 转换为行
        for date_str, stats in sorted(daily_stats.items()):
            first_hour = ""
            last_hour = ""
            if stats["first_msg_time"]:
                try:
                    first_hour = datetime.fromtimestamp(stats["first_msg_time"]).strftime("%H:%M")
                except (ValueError, OSError, TypeError):
                    pass
            if stats["last_msg_time"]:
                try:
                    last_hour = datetime.fromtimestamp(stats["last_msg_time"]).strftime("%H:%M")
                except (ValueError, OSError, TypeError):
                    pass
            
            avg_handle = statistics.mean(stats["handle_times"]) if stats["handle_times"] else 0
            
            rows.append({
                "user_id": user_id,
                "user_name": user_name,
                "date": date_str,
                "input_count": stats["input_count"],
                "output_count": stats["output_count"],
                "text_count": stats["text_count"],
                "voice_count": stats["voice_count"],
                "image_count": stats["image_count"],
                "other_count": stats["other_count"],
                "first_message_hour": first_hour,
                "last_message_hour": last_hour,
                "avg_handle_time_seconds": round(avg_handle, 2),
                "pending_count": stats["pending_count"],
                "handled_count": stats["handled_count"],
                "failed_count": stats["failed_count"],
                "canceled_count": stats["canceled_count"],
            })
    
    # 写入 CSV
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    return len(rows)

# ============================================================
# 主函数
# ============================================================
def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="用户指标分析")
    parser.add_argument("--cost", action="store_true", help="只显示成本分析")
    parser.add_argument("--cohort", action="store_true", help="只显示留存分析")
    parser.add_argument("--distribution", action="store_true", help="只显示分层分析")
    parser.add_argument("--trend", action="store_true", help="只显示趋势分析")
    parser.add_argument("--export-csv", action="store_true", help="导出CSV文件")
    parser.add_argument("--output-dir", type=str, default=".", help="CSV输出目录")
    args = parser.parse_args()
    
    # 如果没有指定任何选项，则显示全部
    show_all = not (args.cost or args.cohort or args.distribution or args.trend or args.export_csv)
    
    logger.info("开始用户指标分析...")
    
    # 初始化
    mongo_db = MongoDBBase()
    user_dao = UserDAO()
    
    try:
        # 获取所有用户（排除角色用户）
        users = user_dao.find_users(query={"is_character": {"$ne": True}})
        
        if not users:
            logger.info("未找到任何用户")
            return
        
        logger.info(f"共找到 {len(users)} 个用户")
        
        # CSV 导出
        if args.export_csv:
            output_dir = args.output_dir
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 导出 user_summary.csv
            user_summary_path = os.path.join(output_dir, "user_summary.csv")
            logger.info(f"正在导出 {user_summary_path}...")
            user_count = export_user_summary_csv(users, mongo_db, user_summary_path)
            logger.info(f"已导出 {user_count} 条用户记录到 {user_summary_path}")
            
            # 导出 daily_activity.csv
            daily_activity_path = os.path.join(output_dir, "daily_activity.csv")
            logger.info(f"正在导出 {daily_activity_path}...")
            daily_count = export_daily_activity_csv(users, mongo_db, daily_activity_path)
            logger.info(f"已导出 {daily_count} 条日活跃记录到 {daily_activity_path}")
            
            print(f"\n✅ CSV 导出完成!")
            print(f"   - {user_summary_path} ({user_count} 条用户记录)")
            print(f"   - {daily_activity_path} ({daily_count} 条日活跃记录)")
            return
        
        # 成本分析
        if show_all or args.cost:
            logger.info("正在进行成本分析...")
            cost_data = analyze_cost_metrics(users, mongo_db)
            print_cost_report(cost_data)
        
        # Cohort 留存分析
        if show_all or args.cohort:
            logger.info("正在进行 Cohort 留存分析...")
            cohort_data = analyze_cohort_retention(users, mongo_db)
            print_cohort_report(cohort_data)
        
        # 用户分层分析
        if show_all or args.distribution:
            logger.info("正在进行用户分层分析...")
            dist_data = analyze_user_distribution(users, mongo_db)
            print_distribution_report(dist_data)
        
        # 每日趋势分析
        if show_all or args.trend:
            logger.info("正在进行每日趋势分析...")
            trend_data = analyze_daily_trend(users, mongo_db)
            print_trend_report(trend_data)
        
        print("\n" + "=" * 100)
        logger.info("用户指标分析完成")
        
    except Exception as e:
        logger.error(f"分析过程中发生错误: {e}")
        raise
    finally:
        mongo_db.close()


if __name__ == "__main__":
    main()
