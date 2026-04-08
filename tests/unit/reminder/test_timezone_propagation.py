# tests/unit/reminder/test_timezone_propagation.py
"""
Tests that user timezone is correctly propagated through TimeParser,
ReminderValidator, and ReminderService.

Modules are loaded directly by file path to avoid the agno/openai import
chain triggered by agent/agno_agent/__init__.py.
"""
import importlib.util
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

_ROOT = Path(__file__).parent.parent.parent.parent  # project root


_REMINDER_PKG = str(_ROOT / "agent/agno_agent/tools/reminder")


def _ensure_pkg(dotted: str, path: str = None) -> types.ModuleType:
    """Ensure a package stub exists in sys.modules."""
    if dotted in sys.modules:
        return sys.modules[dotted]
    m = types.ModuleType(dotted)
    m.__path__ = [path] if path else []
    m.__package__ = dotted
    sys.modules[dotted] = m
    return m


def _load(dotted: str, rel_path: str):
    """Load a module by file path, registering it under the given dotted name."""
    if dotted in sys.modules:
        return sys.modules[dotted]
    path = _ROOT / rel_path
    spec = importlib.util.spec_from_file_location(dotted, path, submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    return mod


# Register parent packages for relative imports.
# We do NOT register "agent" as a stub — other test files may need the real
# agent.runner package, and a hollow stub here would shadow it.
# agent.agno_agent is only registered if not already present (same guard).
for _pkg, _path in [
    ("agent.agno_agent", None),
    ("agent.agno_agent.tools", None),
    ("agent.agno_agent.tools.reminder", _REMINDER_PKG),
]:
    _ensure_pkg(_pkg, _path)

# Pre-load the reminder submodules in dependency order (parser first, formatter depends on it)
_parser = _load(
    "agent.agno_agent.tools.reminder.parser",
    "agent/agno_agent/tools/reminder/parser.py",
)
_formatter = _load(
    "agent.agno_agent.tools.reminder.formatter",
    "agent/agno_agent/tools/reminder/formatter.py",
)
_validator = _load(
    "agent.agno_agent.tools.reminder.validator",
    "agent/agno_agent/tools/reminder/validator.py",
)
_service = _load(
    "agent.agno_agent.tools.reminder.service",
    "agent/agno_agent/tools/reminder/service.py",
)

TimeParser = _parser.TimeParser
ReminderValidator = _validator.ReminderValidator
ReminderService = _service.ReminderService


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parser_format_with_date_uses_injected_tz():
    """format_with_date should use provided tz, not hardcoded Asia/Shanghai."""
    tz = ZoneInfo("America/New_York")
    parser = TimeParser(base_timestamp=int(time.time()), tz=tz)
    # 2024-01-15 08:00:00 UTC = 03:00 New York (EST) = 16:00 Shanghai (CST)
    ts = 1705305600
    result = parser.format_with_date(ts)
    # Should show hour 3 (EST), not 16 (Shanghai)
    assert "16" not in result, f"Expected NY time (03:xx), got: {result}"


def test_validator_formats_time_with_injected_tz():
    """Validator duplicate check message should use the injected timezone."""
    tz = ZoneInfo("America/New_York")
    dao = MagicMock()
    ts = 1705305600  # 2024-01-15 08:00 UTC = 03:00 New York
    dao.find_by_title_fuzzy.return_value = [
        {"reminder_id": "r1", "next_trigger_time": ts, "title": "test"}
    ]
    validator = ReminderValidator(dao=dao, user_id="u1", tz=tz)
    result = validator.check_duplicate("test", ts, recurrence_type=None)
    assert result is not None
    # 16 = Shanghai hour, should not appear with NY timezone
    assert "16" not in result["message"], f"Expected NY time in message: {result['message']}"


def test_service_passes_tz_to_parser_and_validator():
    """ReminderService should propagate user_tz to parser and validator."""
    tz = ZoneInfo("America/New_York")
    service = ReminderService(
        user_id="u1",
        character_id="c1",
        conversation_id="cv1",
        base_timestamp=int(time.time()),
        user_tz=tz,
        dao=MagicMock(),
    )
    assert service.parser.tz == tz
    assert service.validator.tz == tz


def test_service_build_reminder_doc_uses_injected_timezone():
    """Reminder documents should persist the parser timezone, not a hardcoded default."""
    tz = ZoneInfo("America/New_York")
    service = ReminderService(
        user_id="u1",
        character_id="c1",
        conversation_id="cv1",
        base_timestamp=int(time.time()),
        user_tz=tz,
        dao=MagicMock(),
    )

    doc = service._build_reminder_doc(
        title="test",
        trigger_time=1705305600,
        recurrence_type=None,
        recurrence_interval=None,
        period_config=None,
    )

    assert doc["timezone"] == "America/New_York"
