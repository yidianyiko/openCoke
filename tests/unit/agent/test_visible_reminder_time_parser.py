import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_AGNO_AGENT_ROOT = _PROJECT_ROOT / "agent" / "agno_agent"
_AGNO_AGENT_TOOLS_ROOT = _AGNO_AGENT_ROOT / "tools"
_DEFERRED_ACTION_ROOT = _AGNO_AGENT_TOOLS_ROOT / "deferred_action"


def _make_package(name: str, path: Path | None = None) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)] if path else []
    mod.__package__ = name
    mod.__spec__ = importlib.util.spec_from_loader(name, loader=None, is_package=True)
    sys.modules[name] = mod
    return mod


def _load_module_by_path(module_name: str, rel_path: str) -> None:
    if module_name in sys.modules:
        return

    path = _PROJECT_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    parent_name, _, attr = module_name.rpartition(".")
    if parent_name in sys.modules:
        setattr(sys.modules[parent_name], attr, mod)


def _ensure_deferred_action_tool_loaded() -> None:
    if "agent.agno_agent.tools.deferred_action.tool" in sys.modules:
        return

    if "agno" not in sys.modules:
        agno_mod = _make_package("agno")
        agno_tools_mod = _make_package("agno.tools")

        def _tool_passthrough(**kwargs):
            def decorator(fn):
                fn.entrypoint = fn
                return fn

            return decorator

        agno_tools_mod.tool = _tool_passthrough
        agno_mod.tools = agno_tools_mod

    if "agent.agno_agent" not in sys.modules:
        _make_package("agent.agno_agent", _AGNO_AGENT_ROOT)
    if "agent.agno_agent.tools" not in sys.modules:
        _make_package("agent.agno_agent.tools", _AGNO_AGENT_TOOLS_ROOT)
    if "agent.agno_agent.tools.deferred_action" not in sys.modules:
        _make_package(
            "agent.agno_agent.tools.deferred_action",
            _DEFERRED_ACTION_ROOT,
        )

    _load_module_by_path(
        "agent.agno_agent.tools.tool_result",
        "agent/agno_agent/tools/tool_result.py",
    )
    _load_module_by_path(
        "agent.agno_agent.tools.deferred_action.time_parser",
        "agent/agno_agent/tools/deferred_action/time_parser.py",
    )
    if "agent.agno_agent.tools.deferred_action.service" not in sys.modules:
        service_mod = types.ModuleType("agent.agno_agent.tools.deferred_action.service")

        class _DeferredActionService:
            pass

        service_mod.DeferredActionService = _DeferredActionService
        sys.modules["agent.agno_agent.tools.deferred_action.service"] = service_mod
        sys.modules["agent.agno_agent.tools.deferred_action"].service = service_mod
    _load_module_by_path(
        "agent.agno_agent.tools.deferred_action.tool",
        "agent/agno_agent/tools/deferred_action/tool.py",
    )


_ensure_deferred_action_tool_loaded()


def test_parse_visible_reminder_time_marks_absolute_delay():
    from agent.agno_agent.tools.deferred_action.time_parser import (
        parse_visible_reminder_time,
    )

    for trigger_time, offset_hours in (
        ("3小时后", 3),
        ("3个小时后", 3),
        ("2钟头后", 2),
        ("2个钟头后", 2),
    ):
        parsed = parse_visible_reminder_time(
            trigger_time,
            timezone="Asia/Tokyo",
            base_timestamp=1770000000,
        )

        assert parsed["schedule_kind"] == "absolute_delay"
        assert parsed["fixed_timezone"] is False
        assert parsed["dtstart"] == datetime.fromtimestamp(
            1770000000 + offset_hours * 3600,
            tz=ZoneInfo("Asia/Tokyo"),
        )


def test_parse_visible_reminder_time_marks_floating_local_for_named_time():
    from agent.agno_agent.tools.deferred_action.time_parser import (
        parse_visible_reminder_time,
    )

    base_timestamp = 1770000000
    parsed = parse_visible_reminder_time(
        "明天早上9点",
        timezone="Asia/Tokyo",
        base_timestamp=base_timestamp,
    )
    expected_day = datetime.fromtimestamp(
        base_timestamp,
        tz=ZoneInfo("Asia/Tokyo"),
    ) + timedelta(days=1)

    assert parsed["schedule_kind"] == "floating_local"
    assert parsed["fixed_timezone"] is False
    assert parsed["dtstart"] == datetime(
        expected_day.year,
        expected_day.month,
        expected_day.day,
        9,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


@patch("agent.agno_agent.tools.deferred_action.tool.DeferredActionService")
@patch("agent.agno_agent.tools.deferred_action.tool.parse_visible_reminder_time")
def test_visible_reminder_tool_create_uses_effective_timezone(
    mock_parse_time,
    mock_service_class,
):
    from agent.agno_agent.tools.deferred_action.tool import (
        set_deferred_action_session_state,
        visible_reminder_tool,
    )

    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Europe/London"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
        "input_timestamp": 1770000000,
    }
    mock_parse_time.return_value = {
        "dtstart": datetime(2026, 2, 1, 12, 0, tzinfo=ZoneInfo("Europe/London")),
        "schedule_kind": "absolute_delay",
        "fixed_timezone": False,
    }
    mock_service = MagicMock()
    mock_service.create_visible_reminder.return_value = {"title": "开会"}
    mock_service_class.return_value = mock_service

    set_deferred_action_session_state(session_state)
    visible_reminder_tool.entrypoint(
        action="create",
        title="开会",
        trigger_time="3小时后",
    )

    mock_parse_time.assert_called_once_with(
        "3小时后",
        timezone="Europe/London",
        base_timestamp=1770000000,
    )
    mock_service.create_visible_reminder.assert_called_once_with(
        user_id="user-1",
        character_id="char-1",
        conversation_id="conv-1",
        title="开会",
        dtstart=mock_parse_time.return_value["dtstart"],
        timezone="Europe/London",
        rrule=None,
        schedule_kind="absolute_delay",
        fixed_timezone=False,
    )


@patch("agent.agno_agent.tools.deferred_action.tool.DeferredActionService")
@patch("agent.agno_agent.tools.deferred_action.tool.parse_visible_reminder_time")
def test_visible_reminder_tool_update_uses_effective_timezone(
    mock_parse_time,
    mock_service_class,
):
    from agent.agno_agent.tools.deferred_action.tool import (
        set_deferred_action_session_state,
        visible_reminder_tool,
    )

    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Europe/London"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
        "input_timestamp": 1770000000,
    }
    mock_parse_time.return_value = {
        "dtstart": datetime(2026, 2, 1, 12, 0, tzinfo=ZoneInfo("Europe/London")),
        "schedule_kind": "absolute_delay",
        "fixed_timezone": False,
    }
    mock_service = MagicMock()
    mock_service.update_visible_reminder.return_value = {"title": "开会"}
    mock_service_class.return_value = mock_service

    set_deferred_action_session_state(session_state)
    visible_reminder_tool.entrypoint(
        action="update",
        reminder_id="rem-1",
        new_trigger_time="2个钟头后",
    )

    mock_parse_time.assert_called_once_with(
        "2个钟头后",
        timezone="Europe/London",
        base_timestamp=1770000000,
    )
    mock_service.update_visible_reminder.assert_called_once_with(
        action_id="rem-1",
        user_id="user-1",
        dtstart=mock_parse_time.return_value["dtstart"],
        timezone="Europe/London",
        schedule_kind="absolute_delay",
        fixed_timezone=False,
    )
