# -*- coding: utf-8 -*-
"""
Reminder Tool for Agno Agent

This tool provides reminder management capabilities:
- Create new reminders
- Update existing reminders
- Delete reminders
- List/filter reminders
- Complete reminders
- Batch operations

Supports:
- Relative time parsing (e.g., "30分钟后", "明天")
- Absolute time parsing
- Recurrence types: daily, weekly, monthly, yearly
- GTD inbox tasks (no time)
- Time period reminders

Requirements: 3.2, 3.3, 3.4

Refactored: Uses layered architecture with service layer
"""

import contextvars
import logging
from typing import Optional

from agno.tools import tool

from .reminder import ReminderService

logger = logging.getLogger(__name__)


# ========== contextvars Session State Management ==========
# Preserves async isolation for multi-user concurrent processing

_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "session_state", default={}
)
_context_session_state_ref: contextvars.ContextVar[Optional[dict]] = (
    contextvars.ContextVar("session_state_ref", default=None)
)
_context_session_operations: contextvars.ContextVar[list] = contextvars.ContextVar(
    "session_operations", default=[]
)


def set_reminder_session_state(session_state: dict):
    """
    Set session state for current coroutine.

    Uses contextvars to ensure isolation between different async contexts,
    preventing cross-user data contamination in asyncio concurrent processing.

    Args:
        session_state: Session state dict with user, conversation, etc.
    """
    _context_session_state.set(session_state or {})
    _context_session_state_ref.set(session_state or None)
    _context_session_operations.set([])

    user_id = str(session_state.get("user", {}).get("_id", "")) if session_state else ""
    logger.debug(f"set_reminder_session_state: user_id={user_id}")


def _get_current_session_state() -> dict:
    """Get current coroutine's session_state from contextvars."""
    return _context_session_state.get()


def _get_session_operations() -> list:
    """Get current coroutine's operations record."""
    ops = _context_session_operations.get()
    if ops is None:
        ops = []
        _context_session_operations.set(ops)
    return ops


def _check_operation_allowed(action: str) -> tuple[bool, str]:
    """Check if operation is allowed (prevents circular calls)."""
    session_operations = _get_session_operations()

    if action == "batch":
        if session_operations:
            return False, "batch 操作必须是唯一的操作，不能与其他操作混用"
    elif "batch" in session_operations:
        return False, "已执行 batch 操作，不能再执行其他操作"

    if action in session_operations:
        return False, f"{action} 操作只能执行一次"

    session_operations.append(action)
    logger.debug(f"操作记录: {session_operations}")
    return True, ""


def _save_reminder_result_to_session(
    message: str,
    session_state: Optional[dict] = None,
    user_intent: Optional[str] = None,
    action_executed: Optional[str] = None,
    intent_fulfilled: bool = True,
    details: Optional[dict] = None,
):
    """Save reminder operation result to session_state for Agent context."""
    if session_state is None:
        session_state = _get_current_session_state()

    # Backward compatibility
    session_state["【提醒设置工具消息】"] = message

    # Structured context
    if user_intent is None:
        user_intent = "提醒操作"
    if action_executed is None:
        action_executed = "unknown"

    tool_execution_context = {
        "user_intent": user_intent,
        "action_executed": action_executed,
        "intent_fulfilled": intent_fulfilled,
        "result_summary": message,
    }
    if details:
        tool_execution_context["details"] = details

    session_state["tool_execution_context"] = tool_execution_context

    # Sync ref if exists
    session_state_ref = _context_session_state_ref.get()
    if session_state_ref is not None and session_state_ref is not session_state:
        session_state_ref["【提醒设置工具消息】"] = message
        session_state_ref["tool_execution_context"] = tool_execution_context

    logger.info(f"提醒结果已写入 session_state: {message}")


# ========== Tool Entry Point ==========


@tool(
    stop_after_tool_call=True,
    description="""提醒管理工具，用于创建、更新、删除、查询提醒.支持单次提醒、周期提醒和时间段提醒.

## 操作类型 (action)
- "create": 创建单个提醒
- "batch": 批量操作（推荐），一次调用执行多个操作（创建/更新/删除的任意组合）
- "update": 更新提醒（按关键字匹配）
- "delete": 删除提醒（按关键字匹配）
- "filter": 查询提醒（支持灵活的筛选组合）
- "complete": 完成提醒（按关键字匹配）

## 单个操作参数

### create 参数
- title: 提醒标题（必需），如"开会"、"喝水"
- trigger_time: 触发时间（可选），格式"xxxx年xx月xx日xx时xx分"或"30分钟后"。为 None 时创建无时间任务（存入 inbox）
- recurrence_type: 周期类型，可选值: "none"(默认)、"daily"、"weekly"、"monthly"、"interval"
- recurrence_interval: 周期间隔数，默认1（interval类型时单位为分钟）
- period_start/period_end: 时间段，格式 "HH:MM"
- period_days: 生效星期，格式 "1,2,3,4,5，6，7"

### 重复提醒频率限制（系统强制执行）
- 分钟级别（interval < 60分钟）的无限重复提醒：禁止创建（频率过高会导致服务被限制）
- 时间段提醒（设置了period_start/period_end）：最小间隔25分钟
- 小时级别以上的无限重复提醒：允许，但默认10次上限

### update 参数（按关键字匹配）
- keyword: 关键字，模糊匹配要修改的提醒标题（必需）
- new_title: 新标题（可选）
- new_trigger_time: 新触发时间（可选）

### delete 参数（按关键字匹配）
- keyword: 关键字，模糊匹配要删除的提醒标题（必需）
- 使用 "*" 作为 keyword 可删除所有提醒

### filter 参数（查询提醒，替代原 list 操作）
- status: 状态筛选，可选值列表: ["active", "triggered", "completed"]，默认 ["active"]
- reminder_type: 提醒类型，可选值: "one_time" | "recurring"
- keyword: 关键字搜索，模糊匹配 title
- trigger_after: 时间范围开始，格式"xxxx年xx月xx日xx时xx分"或"今天00:00"
- trigger_before: 时间范围结束，格式"xxxx年xx月xx日xx时xx分"或"今天23:59"

### complete 参数（完成提醒）
- keyword: 关键字，模糊匹配要完成的提醒标题（必需）

## 批量操作 (action="batch")-推荐用于复杂场景

当用户消息包含多个操作时使用，一次调用完成所有操作.

参数:
- operations: JSON字符串，包含操作列表.每个操作包含 action 和对应参数.

格式:
```
[
  {"action": "delete", "keyword": "泡衣服"},
  {"action": "create", "title": "喝水", "trigger_time": "2025年12月24日15时00分"},
  {"action": "update", "keyword": "开会", "new_trigger_time": "2025年12月25日10时00分"}
]
```

示例1："把泡衣服的提醒删掉，再帮我加一个喝水提醒"
-> action="batch", operations='[{"action":"delete","keyword":"泡衣服"},{"action":"create","title":"喝水","trigger_time":"..."}]'

示例2："帮我设置三个提醒：8点起床、12点吃饭、6点下班"
-> action="batch", operations='[{"action":"create","title":"起床","trigger_time":"..."},{"action":"create","title":"吃饭","trigger_time":"..."},{"action":"create","title":"下班","trigger_time":"..."}]'

示例3："删除游泳那个提醒，把开会改到明天，再加一个新提醒"
-> action="batch", operations='[{"action":"delete","keyword":"游泳"},{"action":"update","keyword":"开会","new_trigger_time":"..."},{"action":"create","title":"...","trigger_time":"..."}]'

注意: 时间格式必须是"xxxx年xx月xx日xx时xx分"，不支持"下午3点"等格式.
""",
)
def reminder_tool(
    action: Optional[str] = None,
    session_state: Optional[dict] = None,
    title: Optional[str] = None,
    trigger_time: Optional[str] = None,
    action_template: Optional[str] = None,
    keyword: Optional[str] = None,
    new_title: Optional[str] = None,
    new_trigger_time: Optional[str] = None,
    recurrence_type: str = "none",
    recurrence_interval: int = 1,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    period_days: Optional[str] = None,
    operations: Optional[str] = None,
    status: Optional[str] = None,
    reminder_type: Optional[str] = None,
    trigger_after: Optional[str] = None,
    trigger_before: Optional[str] = None,
    include_all: bool = False,
) -> dict:
    """
    Reminder management tool with keyword-based operations.

    This is the thin tool layer that dispatches to ReminderService.
    """
    # Use Agno-injected session_state, fallback to contextvars
    current_session_state = (
        session_state if session_state else _get_current_session_state()
    )
    if session_state:
        _context_session_state.set(session_state)

    # Handle nested action parameter (LLM sometimes passes this way)
    if isinstance(action, dict) and "action" in action:
        action = action["action"]

    # Handle missing action
    if action is None:
        error_message = "操作类型缺失，请指定 action 参数（create/batch/update/delete/filter/complete）"
        logger.error("reminder_tool: action 参数缺失，LLM 未正确传递")
        _save_reminder_result_to_session(
            f"提醒操作失败：{error_message}",
            user_intent="提醒操作",
            action_executed="unknown",
            intent_fulfilled=False,
            details={"error": "action_missing"},
        )
        return {
            "ok": False,
            "error": error_message,
        }

    # Validate action
    valid_actions = (
        "create",
        "batch",
        "update",
        "delete",
        "filter",
        "complete",
        "list",
    )
    if action not in valid_actions:
        return {
            "ok": False,
            "error": f"不支持的操作类型: {action}，支持的操作: {valid_actions}",
        }

    # Check operation allowance (prevent circular calls)
    allowed, error_msg = _check_operation_allowed(action)
    if not allowed:
        logger.warning(f"操作被拒绝: action={action}, reason={error_msg}")
        _save_reminder_result_to_session(f"操作被拒绝：{error_msg}")
        return {"ok": False, "error": error_msg}

    # Extract context from session_state
    user_id = str(current_session_state.get("user", {}).get("_id", ""))
    character_id = str(current_session_state.get("character", {}).get("_id", ""))
    conversation_id = str(current_session_state.get("conversation", {}).get("_id", ""))
    message_timestamp = current_session_state.get("input_timestamp")

    if not user_id and action in (
        "create",
        "batch",
        "filter",
        "update",
        "delete",
        "complete",
        "list",
    ):
        logger.warning("reminder_tool: user_id not found in session_state")
        return {"ok": False, "error": "无法获取用户信息，请稍后重试"}

    # Create service instance
    service = ReminderService(
        user_id=user_id,
        character_id=character_id,
        conversation_id=conversation_id,
        base_timestamp=message_timestamp,
        session_state=current_session_state,
    )

    try:
        result = None

        if action == "create":
            result = service.create(
                title=title,
                trigger_time=trigger_time,
                action_template=action_template,
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
                period_start=period_start,
                period_end=period_end,
                period_days=period_days,
            )

        elif action == "batch":
            result = service.batch(operations=operations)

        elif action == "update":
            result = service.update(
                keyword=keyword,
                new_title=new_title,
                new_trigger_time=new_trigger_time,
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
            )

        elif action == "delete":
            result = service.delete(
                keyword=keyword,
                session_state=current_session_state,
            )

        elif action == "filter":
            result = service.filter(
                status=status,
                reminder_type=reminder_type,
                keyword=keyword,
                trigger_after=trigger_after,
                trigger_before=trigger_before,
            )

        elif action == "complete":
            result = service.complete(
                keyword=keyword,
                session_state=current_session_state,
            )

        elif action == "list":
            # Backward compatibility: redirect to filter
            logger.warning(
                "reminder_tool: 'list' action is deprecated, use 'filter' instead"
            )
            result = service.filter(
                status='["active"]' if not include_all else None,
            )

        else:
            result = {"ok": False, "error": f"不支持的操作类型: {action}"}

        # Save result to session
        _save_result_to_session(action, result)

        return result

    except Exception as e:
        logger.error(f"Error in reminder_tool: {e}")
        _save_reminder_result_to_session(
            f"提醒操作失败：{str(e)}",
            user_intent="提醒操作",
            action_executed=action or "unknown",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}

    finally:
        service.close()


def _save_result_to_session(action: str, result: dict):
    """Save operation result to session with appropriate intent metadata."""
    intent_map = {
        "create": ("创建提醒", "create"),
        "batch": ("批量操作", "batch"),
        "update": ("更新提醒", "update"),
        "delete": ("删除提醒", "delete"),
        "filter": ("查询提醒", "filter"),
        "complete": ("完成提醒", "complete"),
        "list": ("查询提醒", "list"),
    }

    user_intent, action_executed = intent_map.get(action, ("提醒操作", "unknown"))
    intent_fulfilled = result.get("ok", False)

    _save_reminder_result_to_session(
        message=result.get("message", f"操作{'成功' if intent_fulfilled else '失败'}"),
        user_intent=user_intent,
        action_executed=action_executed,
        intent_fulfilled=intent_fulfilled,
        details={"status": result.get("status")} if intent_fulfilled else None,
    )
