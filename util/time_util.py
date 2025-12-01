import sys
sys.path.append(".")
import re
from datetime import datetime, timedelta

def timestamp2str(timestamp, week=False):
    dt_object = datetime.fromtimestamp(timestamp)
    result =  dt_object.strftime('%Y年%m月%d日%H时%M分')
    
    if week:
        week_cn = ""
        week_en = dt_object.strftime('%A')
        if week_en == "Monday":
            week_cn = "星期一"
        if week_en == "Tuesday":
            week_cn = "星期二"
        if week_en == "Wednesday":
            week_cn = "星期三"
        if week_en == "Thursday":
            week_cn = "星期四"
        if week_en == "Friday":
            week_cn = "星期五"
        if week_en == "Saturday":
            week_cn = "星期六"
        if week_en == "Sunday":
            week_cn = "星期日"

        result = result + " " + week_cn
    
    return result

def str2timestamp(time_str, format="%Y年%m月%d日%H时%M分"):
    try:
    # 尝试将字符串转换为datetime对象
        dt = datetime.strptime(time_str, format)
    except ValueError as e:
        return None
    except Exception as e:
        return None
    
    return int(dt.timestamp())

from datetime import datetime

def date2str(timestamp, week=False):
    dt_object = datetime.fromtimestamp(timestamp)
    result =  dt_object.strftime('%Y年%m月%d日')
    
    if week:
        week_cn = ""
        week_en = dt_object.strftime('%A')
        if week_en == "Monday":
            week_cn = "星期一"
        if week_en == "Tuesday":
            week_cn = "星期二"
        if week_en == "Wednesday":
            week_cn = "星期三"
        if week_en == "Thursday":
            week_cn = "星期四"
        if week_en == "Friday":
            week_cn = "星期五"
        if week_en == "Saturday":
            week_cn = "星期六"
        if week_en == "Sunday":
            week_cn = "星期日"

        result = result + " " + week_cn
    
    return result

def parse_relative_time(text, base_timestamp=None):
    """
    解析相对时间表达
    
    Args:
        text: 时间文本，如"30分钟后"、"2小时后"、"明天"
        base_timestamp: 基准时间戳，默认为当前时间
        
    Returns:
        int: 解析后的时间戳，失败返回 None
    """
    if base_timestamp is None:
        base_timestamp = int(datetime.now().timestamp())
    
    base_dt = datetime.fromtimestamp(base_timestamp)
    
    # 相对时间模式
    patterns = [
        # 分钟
        (r'(\d+)\s*分钟[后之]后?', lambda m: base_timestamp + int(m.group(1)) * 60),
        # 小时
        (r'(\d+)\s*[个]?小时[后之]后?', lambda m: base_timestamp + int(m.group(1)) * 3600),
        (r'(\d+)\s*[个]?钟头[后之]后?', lambda m: base_timestamp + int(m.group(1)) * 3600),
        # 天
        (r'(\d+)\s*天[后之]后?', lambda m: base_timestamp + int(m.group(1)) * 86400),
        # 明天
        (r'明天', lambda m: int((base_dt + timedelta(days=1)).replace(hour=9, minute=0, second=0).timestamp())),
        # 后天
        (r'后天', lambda m: int((base_dt + timedelta(days=2)).replace(hour=9, minute=0, second=0).timestamp())),
        # 下周
        (r'下周', lambda m: int((base_dt + timedelta(days=7)).replace(hour=9, minute=0, second=0).timestamp())),
    ]
    
    for pattern, calculator in patterns:
        match = re.search(pattern, text)
        if match:
            return calculator(match)
    
    return None


def calculate_next_recurrence(current_time, recurrence_type, interval=1):
    """
    计算下次周期提醒时间
    
    Args:
        current_time: 当前触发时间戳
        recurrence_type: 周期类型 (daily/weekly/monthly/yearly)
        interval: 间隔数
        
    Returns:
        int: 下次触发时间戳
    """
    current_dt = datetime.fromtimestamp(current_time)
    
    if recurrence_type == "daily":
        next_dt = current_dt + timedelta(days=interval)
    elif recurrence_type == "weekly":
        next_dt = current_dt + timedelta(weeks=interval)
    elif recurrence_type == "monthly":
        next_dt = current_dt + timedelta(days=30 * interval)
    elif recurrence_type == "yearly":
        next_dt = current_dt + timedelta(days=365 * interval)
    elif recurrence_type == "hourly":
        next_dt = current_dt + timedelta(hours=interval)
    elif recurrence_type == "interval":
        next_dt = current_dt + timedelta(minutes=interval)
    else:
        return None
    
    return int(next_dt.timestamp())


def is_time_in_past(timestamp):
    """判断时间是否已过期"""
    return timestamp < int(datetime.now().timestamp())


def format_time_friendly(timestamp):
    """
    将时间戳格式化为友好的文本
    
    Args:
        timestamp: Unix时间戳
        
    Returns:
        str: 友好的时间文本，如"明天上午9点"
    """
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    
    # 计算天数差
    days_diff = (dt.date() - now.date()).days
    
    # 时间部分
    hour = dt.hour
    minute = dt.minute
    
    if hour < 12:
        period = "上午"
    elif hour < 18:
        period = "下午"
        if hour > 12:
            hour = hour - 12
    else:
        period = "晚上"
        if hour > 12:
            hour = hour - 12
    
    time_str = f"{period}{hour}点"
    if minute > 0:
        time_str += f"{minute}分"
    
    # 日期部分
    if days_diff == 0:
        return f"今天{time_str}"
    elif days_diff == 1:
        return f"明天{time_str}"
    elif days_diff == 2:
        return f"后天{time_str}"
    elif days_diff < 7:
        weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][dt.weekday()]
        return f"{weekday}{time_str}"
    else:
        return f"{dt.month}月{dt.day}日{time_str}"
