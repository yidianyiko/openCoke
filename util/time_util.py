import sys

sys.path.append(".")
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from conf.config import CONF
from util.log_util import get_logger

logger = get_logger(__name__)


# ========== BUG-010 fix: Timestamp validation utilities ==========


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

_FALLBACK_TIMEZONE_NAME = "Asia/Shanghai"


def get_default_timezone() -> ZoneInfo:
    configured_name = CONF.get("default_timezone", _FALLBACK_TIMEZONE_NAME)
    try:
        return ZoneInfo(configured_name)
    except Exception:
        logger.warning(
            f"Invalid default timezone '{configured_name}', falling back to {_FALLBACK_TIMEZONE_NAME}"
        )
        return ZoneInfo(_FALLBACK_TIMEZONE_NAME)


def timestamp2str(timestamp, week=False, tz: ZoneInfo = None):
    dt_object = datetime.fromtimestamp(timestamp, tz=tz or get_default_timezone())
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


def str2timestamp(time_str, format="%Y年%m月%d日%H时%M分", tz: ZoneInfo = None):
    try:
        # 尝试将字符串转换为datetime对象
        dt = datetime.strptime(time_str, format)
    except ValueError:
        return None
    except Exception:
        return None

    resolved_tz = tz or get_default_timezone()
    return int(dt.replace(tzinfo=resolved_tz).timestamp())


def date2str(timestamp, week=False, tz: ZoneInfo = None):
    dt_object = datetime.fromtimestamp(timestamp, tz=tz or get_default_timezone())
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


def format_time_friendly(timestamp, tz: ZoneInfo = None):
    """
    将时间戳格式化为友好的文本

    Args:
        timestamp: Unix时间戳

    Returns:
        str: 友好的时间文本，如"明天上午9点"
    """
    _tz = tz or get_default_timezone()
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
