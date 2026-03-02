# Timezone Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all `datetime.now()` and `datetime.fromtimestamp()` calls to use the user's local timezone (inferred from WhatsApp phone country code), eliminating the UTC-vs-CST bug that caused the bot to say "这么晚了" at 8:55 AM.

**Architecture:** Add `get_user_timezone(user_id)` to `time_util.py` that infers timezone from phone country code. Give all formatting/scheduling functions an optional `tz` param defaulting to `ZoneInfo("Asia/Shanghai")`. Fix three call sites: `context.py` (main display time), `agent_background_handler.py` (period-reminder scheduling), and `agent_hardcode_handler.py` (remove `+7200` hack).

**Tech Stack:** Python 3.12, `zoneinfo` (stdlib), `tzdata` pip package (needed on Linux servers with no system tz database)

---

## Task 1: Add `tzdata` to requirements and create `get_user_timezone` in `time_util.py`

**Files:**
- Modify: `requirements.txt`
- Modify: `util/time_util.py`

**Step 1: Add tzdata to requirements.txt**

Open `requirements.txt` and append:
```
tzdata
```
(This provides IANA timezone data on Linux servers that lack it natively — WSL and many Docker containers need it.)

**Step 2: Write a failing test**

File: `tests/unit/test_time_util.py` (create if it doesn't exist, or append to existing)

```python
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
```

**Step 3: Run to confirm failure**

```bash
cd /var/tmp/vibe-kanban/worktrees/f1e4-1-bug/coke
python -m pytest tests/unit/test_time_util.py::test_get_user_timezone_chinese_phone -v
```
Expected: `ImportError` or `AttributeError: module ... has no attribute 'get_user_timezone'`

**Step 4: Implement `get_user_timezone` in `util/time_util.py`**

Add at the top of the file, after the existing imports:

```python
from zoneinfo import ZoneInfo
```

Add this block right after the `# ========== Original time utility functions ==========` comment (before `timestamp2str`):

```python
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
```

**Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/unit/test_time_util.py -k "timezone" -v
```
Expected: 5 tests PASSED

**Step 6: Commit**

```bash
git add requirements.txt util/time_util.py tests/unit/test_time_util.py
git commit -m "feat(timezone): add get_user_timezone() with country-code inference"
```

---

## Task 2: Make all `time_util.py` formatting functions timezone-aware

**Files:**
- Modify: `util/time_util.py`

**Step 1: Write failing tests**

Append to `tests/unit/test_time_util.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from util.time_util import (
    timestamp2str,
    date2str,
    format_time_friendly,
    is_within_time_period,
    calculate_next_period_trigger,
)

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
```

**Step 2: Run to confirm failures**

```bash
python -m pytest tests/unit/test_time_util.py -k "timestamp2str_uses_shanghai or date2str_uses_tz or format_time_friendly or is_within" -v
```
Expected: FAILED (functions don't accept `tz` param yet)

**Step 3: Update `timestamp2str` in `util/time_util.py`**

Replace:
```python
def timestamp2str(timestamp, week=False):
    dt_object = datetime.fromtimestamp(timestamp)
```
With:
```python
def timestamp2str(timestamp, week=False, tz: ZoneInfo = None):
    dt_object = datetime.fromtimestamp(timestamp, tz=tz or _DEFAULT_TZ)
```

Also update the weekday logic to use `dt_object` directly (no other changes needed — `strftime` works on aware datetimes).

**Step 4: Update `date2str` in `util/time_util.py`**

Replace:
```python
def date2str(timestamp, week=False):
    dt_object = datetime.fromtimestamp(timestamp)
```
With:
```python
def date2str(timestamp, week=False, tz: ZoneInfo = None):
    dt_object = datetime.fromtimestamp(timestamp, tz=tz or _DEFAULT_TZ)
```

**Step 5: Update `parse_relative_time` in `util/time_util.py`**

Replace:
```python
    base_dt = datetime.fromtimestamp(base_timestamp)
```
With:
```python
    base_dt = datetime.fromtimestamp(base_timestamp, tz=_DEFAULT_TZ)
```
(Relative time arithmetic is tz-independent; this just ensures `base_dt` is consistent.)

**Step 6: Update `format_time_friendly` in `util/time_util.py`**

Replace:
```python
def format_time_friendly(timestamp):
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
```
With:
```python
def format_time_friendly(timestamp, tz: ZoneInfo = None):
    _tz = tz or _DEFAULT_TZ
    dt = datetime.fromtimestamp(timestamp, tz=_tz)
    now = datetime.now(tz=_tz)
```

**Step 7: Update `is_within_time_period` in `util/time_util.py`**

The function already has `timezone: str = "Asia/Shanghai"` parameter. Just replace the ignored `datetime.fromtimestamp(timestamp)` with:
```python
    _tz = ZoneInfo(timezone)
    dt = datetime.fromtimestamp(timestamp, tz=_tz)
```
Remove the `# TODO: 使用timezone参数进行时区转换` comment.

**Step 8: Update `calculate_next_period_trigger` in `util/time_util.py`**

Same pattern — the function already has `timezone: str = "Asia/Shanghai"`. Replace:
```python
    dt = datetime.fromtimestamp(current_time)
    # TODO: 使用timezone参数进行时区转换
```
With:
```python
    _tz = ZoneInfo(timezone)
    dt = datetime.fromtimestamp(current_time, tz=_tz)
```

Also update all `datetime.combine(...)` calls in this function to pass `tzinfo=_tz`:
```python
        period_start = datetime.combine(check_date, dt_time(start_h, start_m), tzinfo=_tz)
        period_end = datetime.combine(check_date, dt_time(end_h, end_m), tzinfo=_tz)
```

And the `check_dt` construction on day_offset > 0:
```python
            else datetime.combine(check_date, dt_time(start_h, start_m), tzinfo=_tz)
```

**Step 9: Update `is_time_in_past` and `calculate_next_recurrence`**

`is_time_in_past` compares a stored timestamp to now — timezone doesn't matter (both are UTC epoch). No change needed.

`calculate_next_recurrence` just adds timedeltas to a datetime — no display, no tz needed. No change needed.

**Step 10: Run all timezone tests**

```bash
python -m pytest tests/unit/test_time_util.py -v
```
Expected: All PASSED

**Step 11: Commit**

```bash
git add util/time_util.py tests/unit/test_time_util.py
git commit -m "fix(timezone): make all time formatting functions timezone-aware"
```

---

## Task 3: Fix `context.py` to pass user timezone to time functions

**Files:**
- Modify: `agent/runner/context.py`

**Step 1: Read the current call sites**

Lines 215–217 and 254 in `context.py`:
```python
context["conversation"]["conversation_info"]["time_str"] = timestamp2str(
    int(time.time()), week=True
)
...
date_str = date2str(int(time.time()))
```

The user's platform IDs are in `user["platforms"]`. For WhatsApp the key is `"whatsapp"`, for WeChat it's `"wechat"`. We need the platform user ID string.

**Step 2: Add the timezone import and helper call**

At the top of `context.py`, add to the imports:
```python
from util.time_util import date2str, timestamp2str, get_user_timezone
```
(Replace the existing `from util.time_util import date2str, timestamp2str` line.)

**Step 3: Extract user timezone at the top of `context_prepare`**

In `context_prepare`, after `context = {...}` is created (around line 146), add:
```python
    # Infer user timezone from their platform ID (e.g. WhatsApp JID contains country code)
    user_platform_id = next(
        (v.get("id", "") for v in user.get("platforms", {}).values() if v.get("id")),
        "",
    )
    user_tz = get_user_timezone(user_platform_id)
```

**Step 4: Pass `tz` to `timestamp2str` and `date2str`**

Replace line 215–217:
```python
    context["conversation"]["conversation_info"]["time_str"] = timestamp2str(
        int(time.time()), week=True
    )
```
With:
```python
    context["conversation"]["conversation_info"]["time_str"] = timestamp2str(
        int(time.time()), week=True, tz=user_tz
    )
```

Replace line 254:
```python
    date_str = date2str(int(time.time()))
```
With:
```python
    date_str = date2str(int(time.time()), tz=user_tz)
```

**Step 5: Run unit tests to confirm nothing broke**

```bash
python -m pytest tests/unit/ -v --ignore=tests/unit/test_time_util.py -x
```
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add agent/runner/context.py
git commit -m "fix(timezone): pass user timezone to timestamp formatting in context_prepare"
```

---

## Task 4: Fix `agent_hardcode_handler.py` — remove the `+7200` UTC hack

**Files:**
- Modify: `agent/runner/agent_hardcode_handler.py`

**Step 1: Read the current code**

Line 46:
```python
date_str = date2str(int(time.time()) + 7200)
```
This was a manual `+2h` offset to compensate for UTC. Wrong approach, fragile.

**Step 2: Fix it**

Replace:
```python
        date_str = date2str(int(time.time()) + 7200)
```
With:
```python
        date_str = date2str(int(time.time()))
```

Also update the import at the top of the file — add `ZoneInfo` if needed, but actually `date2str` now defaults to `Asia/Shanghai` automatically, so no import change needed.

**Step 3: Run unit tests**

```bash
python -m pytest tests/unit/ -v -x
```
Expected: All PASS

**Step 4: Commit**

```bash
git add agent/runner/agent_hardcode_handler.py
git commit -m "fix(timezone): remove +7200 UTC hack, date2str now defaults to Asia/Shanghai"
```

---

## Task 5: Fix `agent/agno_agent/tools/reminder/parser.py` — tz-aware formatting

**Files:**
- Modify: `agent/agno_agent/tools/reminder/parser.py`

**Step 1: Locate the `datetime.fromtimestamp` call**

Line 100:
```python
dt = datetime.fromtimestamp(timestamp)
```

**Step 2: Fix it**

Add import at the top of the file:
```python
from zoneinfo import ZoneInfo
```

Replace:
```python
        dt = datetime.fromtimestamp(timestamp)
```
With:
```python
        dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("Asia/Shanghai"))
```

**Step 3: Fix the two calls in `validator.py`**

File: `agent/agno_agent/tools/reminder/validator.py`, lines 203 and 506:
```python
time_str = datetime.fromtimestamp(existing_time).strftime(...)
time_str = datetime.fromtimestamp(int(ts)).strftime(...)
```

Add import at the top:
```python
from zoneinfo import ZoneInfo
```

Replace both with:
```python
time_str = datetime.fromtimestamp(existing_time, tz=ZoneInfo("Asia/Shanghai")).strftime(...)
time_str = datetime.fromtimestamp(int(ts), tz=ZoneInfo("Asia/Shanghai")).strftime(...)
```

**Step 4: Run tests**

```bash
python -m pytest tests/unit/ -v -x
```
Expected: All PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/parser.py agent/agno_agent/tools/reminder/validator.py
git commit -m "fix(timezone): use Asia/Shanghai in reminder parser and validator formatting"
```

---

## Task 6: Run full test suite and verify

**Step 1: Run all non-integration tests**

```bash
python -m pytest -m "not integration" -v
```
Expected: All PASS (no regressions)

**Step 2: Smoke-check the time display manually**

```bash
cd /var/tmp/vibe-kanban/worktrees/f1e4-1-bug/coke
python -c "
from zoneinfo import ZoneInfo
from util.time_util import timestamp2str, get_user_timezone
import time

# Simulate a Chinese WhatsApp user
tz = get_user_timezone('8615012345678@s.whatsapp.net')
print('User timezone:', tz)
print('Current time for user:', timestamp2str(int(time.time()), week=True, tz=tz))
"
```
Expected: Timezone = `Asia/Shanghai`, time shows current Beijing time (UTC+8).

**Step 3: Final commit if any cleanup needed, then done**

---

## Summary of Changes

| File | Change |
|------|--------|
| `requirements.txt` | Add `tzdata` |
| `util/time_util.py` | Add `get_user_timezone()`, `_COUNTRY_CODE_TO_TZ`, `_DEFAULT_TZ`; add `tz` param to `timestamp2str`, `date2str`, `format_time_friendly`; fix `is_within_time_period` and `calculate_next_period_trigger` to actually use their `timezone` param |
| `agent/runner/context.py` | Infer `user_tz` from user platforms; pass to `timestamp2str` and `date2str` |
| `agent/runner/agent_hardcode_handler.py` | Remove `+ 7200` hack |
| `agent/agno_agent/tools/reminder/parser.py` | Use `ZoneInfo("Asia/Shanghai")` in `fromtimestamp` |
| `agent/agno_agent/tools/reminder/validator.py` | Use `ZoneInfo("Asia/Shanghai")` in both `fromtimestamp` calls |
| `tests/unit/test_time_util.py` | New tests for all above |
