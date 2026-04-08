from zoneinfo import ZoneInfo
from util.time_util import (
    timestamp2str,
    date2str,
    format_time_friendly,
    is_within_time_period,
    get_user_timezone,
    str2timestamp,
)


def test_get_user_timezone_chinese_phone():
    # +86 → Asia/Shanghai
    assert get_user_timezone("8615012345678@s.whatsapp.net") == ZoneInfo("Asia/Shanghai")


def test_get_user_timezone_brazil():
    # +55 → America/Sao_Paulo
    assert get_user_timezone("5511987654321@s.whatsapp.net") == ZoneInfo("America/Sao_Paulo")


def test_get_user_timezone_unknown_defaults_to_shanghai():
    assert get_user_timezone("99912345@s.whatsapp.net") == ZoneInfo("Asia/Shanghai")


def test_get_user_timezone_plain_string():
    # Non-JID format also works
    assert get_user_timezone("+8613800138000") == ZoneInfo("Asia/Shanghai")


def test_get_user_timezone_none_defaults_to_shanghai():
    assert get_user_timezone(None) == ZoneInfo("Asia/Shanghai")


# A fixed UTC timestamp: 2024-01-15 00:55:00 UTC = 2024-01-15 08:55:00 CST
MIDNIGHT_UTC = 1705280100  # 2024-01-15 00:55 UTC


def test_timestamp2str_uses_shanghai_not_utc():
    result = timestamp2str(MIDNIGHT_UTC, tz=ZoneInfo("Asia/Shanghai"))
    assert "08时55分" in result  # CST, NOT "00时55分" UTC


def test_date2str_uses_tz():
    result = date2str(MIDNIGHT_UTC, tz=ZoneInfo("Asia/Shanghai"))
    assert "2024年01月15日" in result


def test_format_time_friendly_uses_tz():
    result = format_time_friendly(MIDNIGHT_UTC, tz=ZoneInfo("Asia/Shanghai"))
    # 08:55 CST → 上午 period
    assert "上午" in result


def test_is_within_time_period_uses_tz():
    # 00:55 UTC = 08:55 CST → should be within 08:00-12:00
    result = is_within_time_period(
        MIDNIGHT_UTC, "08:00", "12:00", timezone="Asia/Shanghai"
    )
    assert result is True


def test_is_within_time_period_utc_would_fail():
    # Sanity: without tz fix, UTC 00:55 is NOT in 08:00-12:00
    # This documents the bug that existed before the fix
    import datetime as _dt
    dt_utc = _dt.datetime.fromtimestamp(MIDNIGHT_UTC, tz=ZoneInfo("UTC"))
    assert dt_utc.hour == 0  # confirms UTC hour is 0, not 8


def test_str2timestamp_uses_explicit_tz():
    ts = str2timestamp("2024年01月15日03时00分", tz=ZoneInfo("America/New_York"))
    assert ts == 1705305600
