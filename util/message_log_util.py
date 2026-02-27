import json
import os
import re
from typing import Any, Dict, Iterable, Optional

_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)\b(authorization)\s*:\s*bearer\s+[^\s]+"),
        r"\1: Bearer [REDACTED]",
    ),
    (re.compile(r"(?i)\b(bearer)\s+[^\s]+"), r"\1 [REDACTED]"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?key|secret|password|token)\b\s*[:=]\s*([^\s,'\";]+)"
        ),
        r"\1=[REDACTED]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "sk-[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA[REDACTED]"),
]


def _env_flag(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default)
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def redact_text(text: str) -> str:
    if not text:
        return ""
    out = text
    for pattern, repl in _REDACTION_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def normalize_for_log(text: str, keep_newlines: bool = False) -> str:
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\t", " ")
    if keep_newlines:
        s = "\n".join(" ".join(line.split()) for line in s.split("\n"))
    else:
        s = " ".join(s.split())
    return s


def preview_text(
    text: Any,
    *,
    max_chars: Optional[int] = None,
    keep_newlines: bool = False,
    redact: bool = True,
) -> str:
    if text is None:
        return ""
    s = str(text)
    if redact:
        s = redact_text(s)
    s = normalize_for_log(s, keep_newlines=keep_newlines)
    if max_chars is None:
        max_chars = _env_int("LOG_MESSAGE_MAX_CHARS", 200)
    if max_chars > 0 and len(s) > max_chars:
        return s[: max_chars - 1] + "…"
    return s


def should_log_message_content() -> bool:
    return _env_flag("LOG_MESSAGE_CONTENT", "1")


def should_log_full_message_content() -> bool:
    return _env_flag("LOG_MESSAGE_FULL", "0")


def format_std_message_for_log(message: Dict[str, Any]) -> str:
    if not isinstance(message, dict):
        return preview_text(message)

    msg_id = message.get("_id")
    msg_id_str = str(msg_id) if msg_id is not None else ""

    msg_type = message.get("message_type") or message.get("type") or "unknown"
    platform = message.get("platform") or ""
    chatroom = message.get("chatroom_name")
    from_user = message.get("from_user")
    to_user = message.get("to_user")
    ts = message.get("input_timestamp") or message.get("expect_output_timestamp") or ""

    meta = message.get("metadata")
    meta_keys = []
    if isinstance(meta, dict):
        meta_keys = sorted([str(k) for k in meta.keys() if k is not None])[:12]

    content = message.get("message")
    if content is None and "content" in message:
        content = message.get("content")

    max_chars = (
        None
        if should_log_full_message_content()
        else _env_int("LOG_MESSAGE_MAX_CHARS", 200)
    )
    content_preview = preview_text(content, max_chars=max_chars, keep_newlines=False)

    parts = [
        f"id={msg_id_str}" if msg_id_str else None,
        f"ts={ts}" if ts else None,
        f"platform={platform}" if platform else None,
        f"type={msg_type}" if msg_type else None,
        f"chatroom={chatroom}" if chatroom else None,
        f"from={from_user}" if from_user else None,
        f"to={to_user}" if to_user else None,
        f"meta_keys={meta_keys}" if meta_keys else None,
        f"msg={content_preview}" if content_preview != "" else "msg=",
    ]

    return " ".join([p for p in parts if p])


def format_std_messages_for_log(messages: Iterable[Dict[str, Any]]) -> str:
    if messages is None:
        return ""
    try:
        msgs = list(messages)
    except Exception:
        return preview_text(messages)

    max_messages = _env_int("LOG_MESSAGE_MAX_MESSAGES", 8)
    selected = msgs[:max_messages] if max_messages > 0 else msgs
    formatted = [format_std_message_for_log(m) for m in selected]

    more = ""
    if max_messages > 0 and len(msgs) > max_messages:
        more = f" (+{len(msgs) - max_messages} more)"

    return " | ".join(formatted) + more


def safe_json_preview(obj: Any) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        s = str(obj)
    max_chars = (
        None
        if should_log_full_message_content()
        else _env_int("LOG_MESSAGE_MAX_CHARS", 200)
    )
    return preview_text(s, max_chars=max_chars, keep_newlines=False)
