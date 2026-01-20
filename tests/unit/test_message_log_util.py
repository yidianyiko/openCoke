import pytest

from util.message_log_util import (
    format_std_message_for_log,
    format_std_messages_for_log,
    preview_text,
    redact_text,
)


@pytest.mark.unit
def test_redact_text_masks_common_secrets():
    s = "Authorization: Bearer abcdef token=xyz password=123 sk-abcdefghijklmnopqrstuvwxyz"
    out = redact_text(s)
    assert "Bearer [REDACTED]" in out
    assert "token=[REDACTED]" in out
    assert "password=[REDACTED]" in out
    assert "sk-[REDACTED]" in out


@pytest.mark.unit
def test_preview_text_truncates_by_env(monkeypatch):
    monkeypatch.setenv("LOG_MESSAGE_MAX_CHARS", "10")
    out = preview_text("1234567890ABCDEFG")
    assert out.endswith("…")
    assert len(out) == 10


@pytest.mark.unit
def test_format_std_message_for_log_includes_key_fields(monkeypatch):
    monkeypatch.setenv("LOG_MESSAGE_MAX_CHARS", "50")
    msg = {
        "_id": "m1",
        "input_timestamp": 1,
        "platform": "wechat",
        "message_type": "text",
        "from_user": "u1",
        "to_user": "c1",
        "message": "hello",
        "metadata": {"k": "v"},
    }
    out = format_std_message_for_log(msg)
    assert "id=m1" in out
    assert "platform=wechat" in out
    assert "type=text" in out
    assert "from=u1" in out
    assert "to=c1" in out
    assert "msg=hello" in out


@pytest.mark.unit
def test_format_std_messages_for_log_limits_count(monkeypatch):
    monkeypatch.setenv("LOG_MESSAGE_MAX_MESSAGES", "2")
    msgs = [
        {"_id": "m1", "message_type": "text", "message": "a"},
        {"_id": "m2", "message_type": "text", "message": "b"},
        {"_id": "m3", "message_type": "text", "message": "c"},
    ]
    out = format_std_messages_for_log(msgs)
    assert "id=m1" in out
    assert "id=m2" in out
    assert "id=m3" not in out
    assert "+1 more" in out
