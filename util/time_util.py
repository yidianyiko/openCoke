import sys

sys.path.append(".")
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from util.log_util import get_logger

logger = get_logger(__name__)


# ========== BUG-010 fix: Timestamp validation utilities ==========


def get_current_timestamp():
    """Return the current Unix timestamp as an integer."""
    return int(time.time())


def validate_timestamp(value, field_name="timestamp", default_to_now=True):
    """
    Validate and convert a value to a valid Unix timestamp (int).

    Args:
        value: The value to validate (can be int, float, str, or None)
        field_name: Name of the field for logging purposes
        default_to_now: If True, return current time for invalid values;
                        if False, return None for invalid values

    Returns:
        int: Valid Unix timestamp, or None if invalid and default_to_now=False

    Examples:
        >>> validate_timestamp(1703500800)  # int
        1703500800
        >>> validate_timestamp(1703500800.5)  # float
        1703500800
        >>> validate_timestamp("1703500800")  # numeric string
        1703500800
        >>> validate_timestamp(None)  # None -> current time
        <current timestamp>
        >>> validate_timestamp("not_a_timestamp")  # invalid -> current time
        <current timestamp>
    """
    if value is None:
        if default_to_now:
            return int(time.time())
        return None

    if isinstance(value, int):
        # Validate reasonable range (year 2000 to year 2100)
        if 946684800 <= value <= 4102444800:
            return value
        # Might be milliseconds, convert to seconds
        if 946684800000 <= value <= 4102444800000:
            return int(value / 1000)
        logger.warning(f"Timestamp {field_name} out of range: {value}")
        return int(time.time()) if default_to_now else None

    if isinstance(value, float):
        return validate_timestamp(int(value), field_name, default_to_now)

    if isinstance(value, str):
        # Try to parse as numeric string
        try:
            numeric_value = float(value)
            return validate_timestamp(int(numeric_value), field_name, default_to_now)
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid {field_name} string: '{value}', "
                f"{'using current time' if default_to_now else 'returning None'}"
            )
            return int(time.time()) if default_to_now else None

    # Unknown type
    logger.warning(
        f"Invalid {field_name} type: {type(value).__name__}, "
        f"{'using current time' if default_to_now else 'returning None'}"
    )
    return int(time.time()) if default_to_now else None


def safe_timestamp_compare(ts, reference, default_result=False):
    """
    Safely compare a timestamp with a reference value.

    Args:
        ts: Timestamp to compare (may be invalid)
        reference: Reference timestamp (int)
        default_result: Result to return if ts is invalid

    Returns:
        bool: True if ts <= reference, False otherwise, or default_result if invalid
    """
    validated_ts = validate_timestamp(ts, "compare_ts", default_to_now=False)
    if validated_ts is None:
        return default_result
    return validated_ts <= reference


def get_message_timestamp(message, default_to_now=True):
    """
    Extract and validate timestamp from a message dict.

    Checks 'input_timestamp' first, then 'expect_output_timestamp'.

    Args:
        message: Message dict
        default_to_now: If True, return current time if no valid timestamp found

    Returns:
        int: Valid timestamp, or None if not found and default_to_now=False
    """
    if not isinstance(message, dict):
        return int(time.time()) if default_to_now else None

    # Try input_timestamp first
    if "input_timestamp" in message:
        ts = validate_timestamp(
            message["input_timestamp"], "input_timestamp", default_to_now=False
        )
        if ts is not None:
            return ts

    # Try expect_output_timestamp
    if "expect_output_timestamp" in message:
        ts = validate_timestamp(
            message["expect_output_timestamp"],
            "expect_output_timestamp",
            default_to_now=False,
        )
        if ts is not None:
            return ts

    return int(time.time()) if default_to_now else None


# ========== Original time utility functions ==========

# Maps phone country code prefixes (longest match wins) to IANA timezone names.
# Covers the most common countries; anything unrecognized falls back to Asia/Shanghai.
_COUNTRY_CODE_TO_TZ: dict[str, str] = {
    "966": "Asia/Riyadh",
    "971": "Asia/Dubai",
    "1":   "America/New_York",
    "7":   "Europe/Moscow",
    "20":  "Africa/Cairo",
    "27":  "Africa/Johannesburg",
    "44":  "Europe/London",
    "49":  "Europe/Berlin",
    "55":  "America/Sao_Paulo",
    "60":  "Asia/Kuala_Lumpur",
    "62":  "Asia/Jakarta",
    "63":  "Asia/Manila",
    "65":  "Asia/Singapore",
    "66":  "Asia/Bangkok",
    "81":  "Asia/Tokyo",
    "82":  "Asia/Seoul",
    "84":  "Asia/Ho_Chi_Minh",
    "86":  "Asia/Shanghai",
    "90":  "Europe/Istanbul",
    "91":  "Asia/Kolkata",
    "92":  "Asia/Karachi",
}

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def get_user_timezone(user_id: str | None) -> ZoneInfo:
    """
    Infer a user's timezone from their WhatsApp JID or phone number.

    Strips the @s.whatsapp.net suffix, then matches the leading digits against
    country-code prefixes (longest match wins). Falls back to Asia/Shanghai.

    Examples:
        "8615012345678@s.whatsapp.net" → ZoneInfo("Asia/Shanghai")
        "5511987654321@s.whatsapp.net" → ZoneInfo("America/Sao_Paulo")
        None                           → ZoneInfo("Asia/Shanghai")
    """
    if not user_id:
        return _DEFAULT_TZ

    # Strip JID suffix and any leading "+"
    digits = user_id.split("@")[0].lstrip("+")

    # Longest-match: try 3-digit prefix, then 2-digit, then 1-digit
    for length in (3, 2, 1):
        prefix = digits[:length]
        if prefix in _COUNTRY_CODE_TO_TZ:
            return ZoneInfo(_COUNTRY_CODE_TO_TZ[prefix])

    return _DEFAULT_TZ


def timestamp2str(timestamp, week=False, tz: ZoneInfo = None):
    dt_object = datetime.fromtimestamp(timestamp, tz=tz or _DEFAULT_TZ)
    result = dt_object.strftime("%Y年%m月%d日%H时%M分")

    if week:
        week_cn = ""
        week_en = dt_object.strftime("%A")
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
    except ValueError:
        return None
    except Exception:
        return None

    return int(dt.timestamp())


def date2str(timestamp, week=False, tz: ZoneInfo = None):
    dt_object = datetime.fromtimestamp(timestamp, tz=tz or _DEFAULT_TZ)
    result = dt_object.strftime("%Y年%m月%d日")

    if week:
        week_cn = ""
        week_en = dt_object.strftime("%A")
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

    base_dt = datetime.fromtimestamp(base_timestamp, tz=_DEFAULT_TZ)

    # 相对时间模式
    patterns = [
        # 分钟
        (r"(\d+)\s*分钟[后之]后?", lambda m: base_timestamp + int(m.group(1)) * 60),
        # 小时
        (
            r"(\d+)\s*[个]?小时[后之]后?",
            lambda m: base_timestamp + int(m.group(1)) * 3600,
        ),
        (
            r"(\d+)\s*[个]?钟头[后之]后?",
            lambda m: base_timestamp + int(m.group(1)) * 3600,
        ),
        # 天
        (r"(\d+)\s*天[后之]后?", lambda m: base_timestamp + int(m.group(1)) * 86400),
        # 明天
        (
            r"明天",
            lambda m: int(
                (base_dt + timedelta(days=1))
                .replace(hour=9, minute=0, second=0)
                .timestamp()
            ),
        ),
        # 后天
        (
            r"后天",
            lambda m: int(
                (base_dt + timedelta(days=2))
                .replace(hour=9, minute=0, second=0)
                .timestamp()
            ),
        ),
        # 下周
        (
            r"下周",
            lambda m: int(
                (base_dt + timedelta(days=7))
                .replace(hour=9, minute=0, second=0)
                .timestamp()
            ),
        ),
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


def format_time_friendly(timestamp, tz: ZoneInfo = None):
    """
    将时间戳格式化为友好的文本

    Args:
        timestamp: Unix时间戳

    Returns:
        str: 友好的时间文本，如"明天上午9点"
    """
    _tz = tz or _DEFAULT_TZ
    dt = datetime.fromtimestamp(timestamp, tz=_tz)
    now = datetime.now(tz=_tz)

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
        weekday = [
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日",
        ][dt.weekday()]
        return f"{weekday}{time_str}"
    else:
        return f"{dt.month}月{dt.day}日{time_str}"


def is_within_time_period(
    timestamp: int,
    start_time: str,
    end_time: str,
    active_days: list = None,
    timezone: str = "Asia/Shanghai",
) -> bool:
    """
    判断给定时间戳是否在指定时间段内

    Args:
        timestamp: Unix 时间戳
        start_time: 开始时间 "HH:MM"
        end_time: 结束时间 "HH:MM"
        active_days: 生效的星期几列表 [1-7]，None 表示每天
        timezone: 时区

    Returns:
        bool: 是否在时间段内
    """
    _tz = ZoneInfo(timezone)
    dt = datetime.fromtimestamp(timestamp, tz=_tz)

    # 检查星期几
    if active_days:
        weekday = dt.isoweekday()  # 1=周一, 7=周日
        if weekday not in active_days:
            return False

    # 解析时间
    start_h, start_m = map(int, start_time.split(":"))
    end_h, end_m = map(int, end_time.split(":"))

    current_minutes = dt.hour * 60 + dt.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    return start_minutes <= current_minutes <= end_minutes


def calculate_next_period_trigger(
    current_time: int,
    interval_minutes: int,
    start_time: str,
    end_time: str,
    active_days: list = None,
    timezone: str = "Asia/Shanghai",
) -> int:
    """
    计算时间段提醒的下次触发时间

    逻辑：
    1. 如果当前在时间段内，返回 current + interval
    2. 如果当前在时间段外，返回下一个有效时间段的开始时间
    3. 如果下次触发超出今天时间段，跳到下一个有效日期

    Args:
        current_time: 当前时间戳
        interval_minutes: 间隔分钟数
        start_time: 时间段开始 "HH:MM"
        end_time: 时间段结束 "HH:MM"
        active_days: 生效的星期几 [1-7]
        timezone: 时区

    Returns:
        int: 下次触发的 Unix 时间戳，或 None（如果无法计算）
    """
    from datetime import time as dt_time

    _tz = ZoneInfo(timezone)
    dt = datetime.fromtimestamp(current_time, tz=_tz)

    start_h, start_m = map(int, start_time.split(":"))
    end_h, end_m = map(int, end_time.split(":"))

    # 尝试最多7天
    for day_offset in range(8):
        check_date = dt.date() + timedelta(days=day_offset)
        check_dt = (
            datetime.combine(check_date, dt.replace(tzinfo=None).time(), tzinfo=_tz)
            if day_offset == 0
            else datetime.combine(check_date, dt_time(start_h, start_m), tzinfo=_tz)
        )
        check_weekday = check_dt.isoweekday()

        # 检查是否是有效日期
        if active_days and check_weekday not in active_days:
            continue

        # 计算该日期的时间段
        period_start = datetime.combine(check_date, dt_time(start_h, start_m), tzinfo=_tz)
        period_end = datetime.combine(check_date, dt_time(end_h, end_m), tzinfo=_tz)

        if day_offset == 0:
            # 今天：检查是否还在时间段内
            next_trigger = dt + timedelta(minutes=interval_minutes)
            if period_start <= next_trigger <= period_end:
                return int(next_trigger.timestamp())
            elif dt < period_start:
                # 还没到开始时间
                return int(period_start.timestamp())
        else:
            # 未来的日期：返回时间段开始时间
            return int(period_start.timestamp())

    return None
