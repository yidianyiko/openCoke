from zoneinfo import ZoneInfo
from util.time_util import get_user_timezone


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
