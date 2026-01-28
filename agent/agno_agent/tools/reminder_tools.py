# -*- coding: utf-8 -*-
"""
Reminder Tool for Agno Agent

This tool provides reminder management capabilities:
- Create new reminders
- Update existing reminders
- Delete reminders
- List user reminders

Supports:
- Relative time parsing (e.g., "30分钟后", "明天")
- Absolute time parsing
- Recurrence types: daily, weekly, monthly, yearly

Requirements: 3.2, 3.3, 3.4

Fix: 使用 contextvars 解决 asyncio 环境下多协程并发时的跨用户数据污染问题
     (threading.local 只能隔离线程，无法隔离同一线程内的不同协程)
"""

import contextvars
import logging
import time
import uuid
from typing import Optional

from agno.tools import tool

from dao.reminder_dao import ReminderDAO
from util.time_util import format_time_friendly, parse_relative_time, str2timestamp
from datetime import datetime

logger = logging.getLogger(__name__)

_DELETE_ALL_WORDS = ["全部", "所有", "清空", "都删", "全删"]


def _get_current_input_messages_text(session_state: Optional[dict] = None) -> str:
    if session_state is None:
        session_state = _get_current_session_state()
    conversation_info = (
        (session_state or {}).get("conversation", {}).get("conversation_info", {}) or {}
    )
    input_messages = conversation_info.get("input_messages") or []
    if not isinstance(input_messages, list) or not input_messages:
        return ""

    texts: list[str] = []
    for msg in input_messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("message")
        if content is None:
            continue
        content_str = str(content).strip()
        if content_str:
            texts.append(content_str)
    return "\n".join(texts)


def _contains_any(text: str, candidates: list[str]) -> bool:
    if not text:
        return False
    for w in candidates:
        if w and w in text:
            return True
    return False


def _get_active_candidates(reminder_dao: ReminderDAO, user_id: str) -> list[dict]:
    try:
        reminders = reminder_dao.filter_reminders(
            user_id=user_id, status_list=["active", "triggered"]
        )
    except Exception:
        reminders = []
    if not isinstance(reminders, list):
        return []
    return reminders


def _summarize_candidates(reminders: list[dict], limit: int = 3) -> tuple[list[dict], str]:
    candidates: list[dict] = []
    lines: list[str] = []
    for r in reminders[:limit]:
        title = str(r.get("title") or "").strip()
        ts = r.get("next_trigger_time")
        time_str = ""
        if isinstance(ts, (int, float)) and ts > 0:
            time_str = datetime.fromtimestamp(int(ts)).strftime("%m月%d日%H:%M")
        if title:
            candidates.append({"title": title, "time": time_str, "reminder_id": r.get("reminder_id")})
            lines.append(f"「{title}」{('(' + time_str + ')') if time_str else ''}")
    return candidates, "、".join(lines)


def _guard_side_effect_action(
    action: str,
    reminder_dao: ReminderDAO,
    user_id: str,
    keyword: Optional[str],
    session_state: Optional[dict] = None,
) -> dict:
    user_text = _get_current_input_messages_text(session_state=session_state).strip()
    kw = (keyword or "").strip()

    if action not in ("delete", "complete"):
        return {"allowed": True}

    if not user_text:
        return {
            "allowed": False,
            "needs_confirmation": True,
            "error": "无法获取用户本轮原文，已阻止执行有副作用的提醒操作",
            "candidates": [],
            "resolved_keyword": None,
            "reason": "missing_user_text",
        }

    active_candidates = _get_active_candidates(reminder_dao, user_id)
    matched_titles = []
    for r in active_candidates:
        title = str(r.get("title") or "").strip()
        if title and title in user_text:
            matched_titles.append(title)
    matched_titles = list(dict.fromkeys(matched_titles))

    if len(matched_titles) == 1:
        return {
            "allowed": True,
            "needs_confirmation": False,
            "error": "",
            "candidates": [],
            "resolved_keyword": matched_titles[0],
            "reason": "matched_active_title_in_user_text",
        }

    if len(matched_titles) > 1:
        candidates, display = _summarize_candidates(active_candidates, limit=3)
        return {
            "allowed": False,
            "needs_confirmation": True,
            "error": "本轮消息同时命中多个提醒，无法确定要操作哪一个",
            "candidates": candidates,
            "resolved_keyword": None,
            "reason": "ambiguous_title_matches",
            "display": display,
        }

    if kw == "*" and action == "delete":
        if _contains_any(user_text, _DELETE_ALL_WORDS):
            return {
                "allowed": True,
                "needs_confirmation": False,
                "error": "",
                "candidates": [],
                "resolved_keyword": None,
                "reason": "explicit_delete_all",
            }
        candidates, display = _summarize_candidates(active_candidates, limit=3)
        return {
            "allowed": False,
            "needs_confirmation": True,
            "error": "删除全部提醒需要用户明确表示“全部/清空/所有”等意图",
            "candidates": candidates,
            "resolved_keyword": None,
            "reason": "delete_all_not_explicit",
            "display": display,
        }

    if kw and kw in user_text:
        return {
            "allowed": True,
            "needs_confirmation": False,
            "error": "",
            "candidates": [],
            "resolved_keyword": kw,
            "reason": "keyword_in_user_text",
        }

    candidates, display = _summarize_candidates(active_candidates, limit=3)
    return {
        "allowed": False,
        "needs_confirmation": True,
        "error": "用户本轮消息未明确包含要操作的提醒关键字或标题",
        "candidates": candidates,
        "resolved_keyword": None,
        "reason": "keyword_not_in_user_text",
        "display": display,
    }


def _parse_trigger_time(
    trigger_time: str, base_timestamp: Optional[int] = None
) -> Optional[int]:
    """
     Parse trigger time from string to timestamp.

     Supports:
    -Relative time: "30分钟后", "2小时后", "明天", "后天", "下周"
    -Absolute time: "2024年12月25日09时00分"

     Args:
         trigger_time: Time string to parse
         base_timestamp: 基准时间戳（用于相对时间计算），默认为当前时间

     Returns:
         Unix timestamp or None if parsing fails
    """
    if not trigger_time:
        return None

    # Try relative time first (使用基准时间戳)
    timestamp = parse_relative_time(trigger_time, base_timestamp)
    if timestamp:
        return timestamp

    # Try absolute time
    timestamp = str2timestamp(trigger_time)
    if timestamp:
        return timestamp

    return None


# 使用 contextvars 存储会话状态，支持 asyncio 协程隔离
# threading.local 只能隔离线程，无法隔离同一线程内的不同协程
# contextvars 可以正确隔离 asyncio 中的不同协程上下文
_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "session_state", default={}
)
_context_session_state_ref: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "session_state_ref", default=None
)
_context_session_operations: contextvars.ContextVar[list] = contextvars.ContextVar(
    "session_operations", default=[]
)


def set_reminder_session_state(session_state: dict):
    """
    设置当前协程的会话状态，供 reminder_tool 使用

    使用 contextvars 确保不同协程之间的 session_state 相互隔离，
    避免 asyncio 并发处理时的跨用户数据污染.
    """
    _context_session_state.set(session_state or {})
    _context_session_state_ref.set(session_state or None)
    _context_session_operations.set([])

    # 记录设置的 user_id，便于调试
    user_id = str(session_state.get("user", {}).get("_id", "")) if session_state else ""
    logger.debug(f"set_reminder_session_state: user_id={user_id}")


def _get_current_session_state() -> dict:
    """获取当前协程的 session_state"""
    return _context_session_state.get()


def _get_session_operations() -> list:
    """获取当前协程的操作记录"""
    ops = _context_session_operations.get()
    if ops is None:
        ops = []
        _context_session_operations.set(ops)
    return ops


def _check_operation_allowed(action: str) -> tuple[bool, str]:
    """
     检查操作是否允许，防止循环调用

     规则：
    -batch 操作只能调用一次（内部可包含多种操作类型）
    -单独的 create/update/delete/list 各只能调用一次
    -batch 之后不能再调用其他操作
    -其他操作之后不能调用 batch

     Args:
         action: 操作类型

     Returns:
         (是否允许, 错误信息)
    """
    session_operations = _get_session_operations()

    # batch 操作的特殊处理
    if action == "batch":
        if session_operations:
            return False, "batch 操作必须是唯一的操作，不能与其他操作混用"
    elif "batch" in session_operations:
        return False, "已执行 batch 操作，不能再执行其他操作"

    # 检查重复操作
    if action in session_operations:
        return False, f"{action} 操作只能执行一次"

    # 记录本次操作
    session_operations.append(action)
    logger.debug(f"操作记录: {session_operations}")
    return True, ""


def _get_missing_info_prompt(missing_fields: list) -> str:
    """
    根据缺少的字段生成友好的提示信息

    注意：这个消息不会直接发给用户，而是供后续流程处理
    """
    prompts = []
    if "title" in missing_fields:
        prompts.append("提醒内容/事项")
    if "trigger_time" in missing_fields:
        prompts.append("提醒时间")

    return f"需要补充: {'、'.join(prompts)}"


def _build_tool_execution_context(
    user_intent: str,
    action_executed: str,
    intent_fulfilled: bool,
    result_summary: str,
    details: Optional[dict] = None,
) -> dict:
    """
    构建结构化的工具执行上下文

    Args:
        user_intent: 从用户消息中识别的意图
        action_executed: 实际执行的操作
        intent_fulfilled: 布尔值，意图是否被满足
        result_summary: 执行结果的语义化描述
        details: 可选的额外详情（如创建的提醒ID、删除的数量等）

    Returns:
        结构化的工具执行上下文字典
    """
    context = {
        "user_intent": user_intent,
        "action_executed": action_executed,
        "intent_fulfilled": intent_fulfilled,
        "result_summary": result_summary,
    }
    if details:
        context["details"] = details
    return context


def _save_reminder_result_to_session(
    message: str,
    session_state: Optional[dict] = None,
    user_intent: Optional[str] = None,
    action_executed: Optional[str] = None,
    intent_fulfilled: bool = True,
    details: Optional[dict] = None,
):
    """
    将提醒操作结果保存到 session_state，供 ChatAgent 作为上下文使用

    Args:
        message: 语义化的操作结果描述
        session_state: 可选的 session_state，如果不提供则使用 contextvars
        user_intent: 从用户消息中识别的意图（可选，用于结构化上下文）
        action_executed: 实际执行的操作（可选，用于结构化上下文）
        intent_fulfilled: 意图是否被满足，默认 True
        details: 可选的额外详情
    """
    if session_state is None:
        session_state = _get_current_session_state()

    # 保留原有的语义化消息（向后兼容）
    session_state["【提醒设置工具消息】"] = message

    # 新增：结构化工具执行上下文
    if user_intent is None:
        user_intent = "提醒操作"
    if action_executed is None:
        action_executed = "unknown"

    tool_execution_context = _build_tool_execution_context(
        user_intent=user_intent,
        action_executed=action_executed,
        intent_fulfilled=intent_fulfilled,
        result_summary=message,
        details=details,
    )
    session_state["tool_execution_context"] = tool_execution_context
    session_state_ref = _context_session_state_ref.get()
    if session_state_ref is not None and session_state_ref is not session_state:
        session_state_ref["【提醒设置工具消息】"] = message
        session_state_ref["tool_execution_context"] = tool_execution_context

    logger.info(f"提醒结果已写入 session_state: {message}")
    logger.debug(f"工具执行上下文: {tool_execution_context}")


# 重要修复 (2025-12-23):
# 添加 stop_after_tool_call=True，让 Agent 在工具执行后立即停止
# 解决问题：LLM 在工具成功执行后不知道如何退出，持续尝试调用工具导致无限循环
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
- period_days: 生效星期，格式 "1,2,3,4,5"

### GTD 无时间任务支持（P0）
- 创建提醒时 trigger_time 可以为 None，任务会存入 inbox（list_id="inbox"）
- 无时间任务不会被定时触发，需要用户手动查看或通过每日汇总了解（P1 功能）

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
→ action="batch", operations='[{"action":"delete","keyword":"泡衣服"},{"action":"create","title":"喝水","trigger_time":"..."}]'

示例2："帮我设置三个提醒：8点起床、12点吃饭、6点下班"
→ action="batch", operations='[{"action":"create","title":"起床","trigger_time":"..."},{"action":"create","title":"吃饭","trigger_time":"..."},{"action":"create","title":"下班","trigger_time":"..."}]'

示例3："删除游泳那个提醒，把开会改到明天，再加一个新提醒"
→ action="batch", operations='[{"action":"delete","keyword":"游泳"},{"action":"update","keyword":"开会","new_trigger_time":"..."},{"action":"create","title":"...","trigger_time":"..."}]'

注意: 时间格式必须是"xxxx年xx月xx日xx时xx分"，不支持"下午3点"等格式.
""",
)
def reminder_tool(
    action: Optional[str] = None,  # LLM 有时会漏传此参数，设为可选以便在函数内处理
    session_state: Optional[dict] = None,  # Agno 框架会自动注入 session_state
    title: Optional[str] = None,
    trigger_time: Optional[str] = None,
    action_template: Optional[str] = None,
    keyword: Optional[str] = None,  # 关键字（update/delete/complete 必需）
    new_title: Optional[str] = None,  # update 时的新标题
    new_trigger_time: Optional[str] = None,  # update 时的新时间
    recurrence_type: str = "none",
    recurrence_interval: int = 1,
    # 时间段提醒参数
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    period_days: Optional[str] = None,
    # 批量操作参数
    operations: Optional[str] = None,
    # filter 操作参数（阶段二新增，替代 list）
    status: Optional[str] = None,  # JSON 字符串，如 '["active", "triggered"]'
    reminder_type: Optional[str] = None,  # "one_time" | "recurring"
    trigger_after: Optional[str] = None,  # 时间范围开始
    trigger_before: Optional[str] = None,  # 时间范围结束
    # list 操作参数（向后兼容，已废弃）
    include_all: bool = False,
) -> dict:
    """
    提醒管理统一工具（基于关键字操作，不使用 ID）

    Args:
        action: 操作类型-"create"、"batch"、"update"、"delete"、"filter"、"complete"
        session_state: Agno 框架自动注入的会话状态
        title: 提醒标题（create 时必需）
        trigger_time: 触发时间（create 时必需）
        action_template: 提醒文案模板（可选）
        keyword: 关键字（update/delete/complete 时必需，模糊匹配标题）
        new_title: 新标题（update 时可选）
        new_trigger_time: 新触发时间（update 时可选）
        recurrence_type: 周期类型，默认"none"
        recurrence_interval: 周期间隔数，默认1
        operations: 批量操作时的操作列表JSON字符串
        status: filter操作的状态筛选，JSON字符串
        reminder_type: filter操作的提醒类型筛选
        trigger_after: filter操作的时间范围开始
        trigger_before: filter操作的时间范围结束
        include_all: list操作时是否包含所有状态（已废弃，使用filter替代）

    Returns:
        操作结果字典
    """
    # 优先使用 Agno 注入的 session_state，否则回退到 contextvars
    current_session_state = (
        session_state if session_state else _get_current_session_state()
    )

    # 同步到 contextvars，确保内部函数也能访问到正确的 session_state
    if session_state:
        _context_session_state.set(session_state)

    # 修正 LLM 可能传递的嵌套参数格式问题
    if isinstance(action, dict) and "action" in action:
        action = action["action"]

    # 处理 action 缺失的情况
    if action is None:
        error_message = (
            "操作类型缺失，请指定 action 参数（create/batch/update/delete/list）"
        )
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
            "error": "操作类型缺失，请指定 action 参数（create/batch/update/delete/filter/complete）",
        }

    # 手动验证 action 值（阶段二：移除 list，新增 filter/complete）
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

    # 检查操作组合是否允许（防止循环调用）
    allowed, error_msg = _check_operation_allowed(action)
    if not allowed:
        logger.warning(f"操作被拒绝: action={action}, reason={error_msg}")
        _save_reminder_result_to_session(f"操作被拒绝：{error_msg}")
        return {"ok": False, "error": error_msg}

    # 从 session_state 获取用户信息
    user_id = str(current_session_state.get("user", {}).get("_id", ""))
    character_id = str(current_session_state.get("character", {}).get("_id", ""))
    conversation_id = str(current_session_state.get("conversation", {}).get("_id", ""))

    if not user_id and action in [
        "create",
        "batch",
        "filter",
        "update",
        "delete",
        "complete",
        "list",
    ]:
        logger.warning("reminder_tool: user_id not found in session_state")
        return {"ok": False, "error": "无法获取用户信息，请稍后重试"}

    reminder_dao = ReminderDAO()

    logger.info(
        f"reminder_tool called: action={action}, title={title}, trigger_time={trigger_time}, user_id={user_id}"
    )

    try:
        # 获取消息的输入时间戳作为相对时间计算的基准
        message_timestamp = current_session_state.get("input_timestamp")

        if action == "create":
            result = _create_reminder(
                reminder_dao=reminder_dao,
                user_id=user_id,
                title=title,
                trigger_time=trigger_time,
                action_template=action_template,
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
                conversation_id=conversation_id,
                character_id=character_id,
                base_timestamp=message_timestamp,
                period_start=period_start,
                period_end=period_end,
                period_days=period_days,
            )
            logger.info(f"reminder_tool create result: {result}")
            return result

        elif action == "batch":
            result = _batch_operations(
                reminder_dao=reminder_dao,
                user_id=user_id,
                operations_json=operations,
                conversation_id=conversation_id,
                character_id=character_id,
                base_timestamp=message_timestamp,
            )
            logger.info(f"reminder_tool batch result: {result}")
            return result

        elif action == "update":
            return _update_reminder_by_keyword(
                reminder_dao=reminder_dao,
                user_id=user_id,
                keyword=keyword,
                new_title=new_title,
                new_trigger_time=new_trigger_time,
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
            )

        elif action == "delete":
            guard = _guard_side_effect_action(
                action="delete",
                reminder_dao=reminder_dao,
                user_id=user_id,
                keyword=keyword,
                session_state=current_session_state,
            )
            if not guard.get("allowed"):
                candidates = guard.get("candidates") or []
                display = guard.get("display") or ""
                semantic_message = (
                    f"提醒删除未执行：{guard.get('error')}"
                    + (f"。可选提醒：{display}" if display else "")
                )
                _save_reminder_result_to_session(
                    semantic_message,
                    user_intent="删除提醒",
                    action_executed="delete",
                    intent_fulfilled=False,
                    details={
                        "reason": guard.get("reason"),
                        "keyword": (keyword or "").strip(),
                        "needs_confirmation": bool(guard.get("needs_confirmation")),
                        "candidates": candidates,
                    },
                )
                return {
                    "ok": False,
                    "error": guard.get("error"),
                    "needs_confirmation": bool(guard.get("needs_confirmation")),
                    "candidates": candidates,
                }
            if guard.get("resolved_keyword") is not None:
                keyword = guard.get("resolved_keyword")
            return _delete_reminder_by_keyword(
                reminder_dao=reminder_dao,
                user_id=user_id,
                keyword=keyword,
            )

        elif action == "filter":
            return _filter_reminders(
                reminder_dao=reminder_dao,
                user_id=user_id,
                status=status,
                reminder_type=reminder_type,
                keyword=keyword,
                trigger_after=trigger_after,
                trigger_before=trigger_before,
                base_timestamp=message_timestamp,
            )

        elif action == "complete":
            guard = _guard_side_effect_action(
                action="complete",
                reminder_dao=reminder_dao,
                user_id=user_id,
                keyword=keyword,
                session_state=current_session_state,
            )
            if not guard.get("allowed"):
                candidates = guard.get("candidates") or []
                display = guard.get("display") or ""
                semantic_message = (
                    f"提醒完成未执行：{guard.get('error')}"
                    + (f"。可选提醒：{display}" if display else "")
                )
                _save_reminder_result_to_session(
                    semantic_message,
                    user_intent="完成提醒",
                    action_executed="complete",
                    intent_fulfilled=False,
                    details={
                        "reason": guard.get("reason"),
                        "keyword": (keyword or "").strip(),
                        "needs_confirmation": bool(guard.get("needs_confirmation")),
                        "candidates": candidates,
                    },
                )
                return {
                    "ok": False,
                    "error": guard.get("error"),
                    "needs_confirmation": bool(guard.get("needs_confirmation")),
                    "candidates": candidates,
                }
            if guard.get("resolved_keyword") is not None:
                keyword = guard.get("resolved_keyword")
            return _complete_reminder(
                reminder_dao=reminder_dao,
                user_id=user_id,
                keyword=keyword,
            )

        elif action == "list":
            # 向后兼容：list 操作重定向到 filter
            logger.warning(
                "reminder_tool: 'list' action is deprecated, use 'filter' instead"
            )
            return _filter_reminders(
                reminder_dao=reminder_dao,
                user_id=user_id,
                status='["active"]' if not include_all else None,
                reminder_type=None,
                keyword=None,
                trigger_after=None,
                trigger_before=None,
                base_timestamp=message_timestamp,
            )

        else:
            return {"ok": False, "error": f"不支持的操作类型: {action}"}

    except Exception as e:
        logger.error(f"Error in reminder_tool: {e}")
        return {"ok": False, "error": str(e)}

    finally:
        reminder_dao.close()


# ========== 创建提醒辅助函数（重构自 _create_reminder，降低复杂度） ==========

# 频率限制常量
_MIN_INTERVAL_INFINITE = 60  # 无限重复提醒最小间隔：60分钟
_MIN_INTERVAL_PERIOD = 25  # 时间段提醒最小间隔：25分钟
_DEFAULT_MAX_TRIGGERS = 10  # 默认最大触发次数
_TIME_TOLERANCE = 60  # 去重时间容差（秒）


def _check_required_fields(
    title: Optional[str], trigger_time: Optional[str]
) -> Optional[dict]:
    """
    检查必要字段是否完整.

    Returns:
        如果缺少字段返回 needs_info 响应，否则返回 None
    """
    missing_fields = []
    draft_info = {}

    if not title:
        missing_fields.append("title")
    else:
        draft_info["title"] = title

    # 移除 trigger_time 必需检查 - GTD P0: 支持无时间任务
    # trigger_time 可选，为 None 时创建无时间任务（存入 inbox）
    if trigger_time:
        draft_info["trigger_time"] = trigger_time

    if not missing_fields:
        return None

    logger.info(
        f"Reminder needs more info: missing={missing_fields}, draft={draft_info}"
    )

    missing_desc = "、".join(
        ["提醒内容" if f == "title" else "提醒时间" for f in missing_fields]
    )
    semantic_message = (
        f"信息不足：用户想设置提醒，但缺少【{missing_desc}】，请询问用户补充"
    )
    _save_reminder_result_to_session(
        semantic_message,
        user_intent="创建提醒",
        action_executed="create",
        intent_fulfilled=False,
        details={"missing_fields": missing_fields, "draft": draft_info},
    )

    return {
        "ok": True,
        "status": "needs_info",
        "missing_fields": missing_fields,
        "draft": draft_info,
        "message": _get_missing_info_prompt(missing_fields),
    }


def _check_frequency_limit(
    recurrence_type: str,
    recurrence_interval: int,
    is_period_reminder: bool,
    user_id: str,
) -> Optional[dict]:
    """
    检查重复提醒频率限制.

    Returns:
        如果频率过高返回错误响应，否则返回 None
    """
    if recurrence_type != "interval":
        return None

    if is_period_reminder:
        if recurrence_interval >= _MIN_INTERVAL_PERIOD:
            return None
        error_msg = (
            f"频率过高：时间段提醒的间隔不能少于{_MIN_INTERVAL_PERIOD}分钟，"
            f"当前设置为每{recurrence_interval}分钟."
            "这可能导致我的服务被限制，也不是 Coke 的设计用途."
        )
        logger.warning(
            f"Rejected period reminder: interval={recurrence_interval}min, user_id={user_id}"
        )
    else:
        if recurrence_interval >= _MIN_INTERVAL_INFINITE:
            return None
        error_msg = (
            f"频率过高：不支持每{recurrence_interval}分钟的无限重复提醒."
            "这可能导致我的服务被限制，也不是 Coke 的设计用途.\n"
            "建议：\n"
            "1. 使用时间段提醒（如「上午9点到下午6点每30分钟提醒」，最小间隔25分钟）\n"
            "2. 或使用小时级别以上的周期（如「每小时」「每天」）"
        )
        logger.warning(
            f"Rejected infinite reminder: interval={recurrence_interval}min, user_id={user_id}"
        )

    _save_reminder_result_to_session(
        f"提醒创建被拒绝：{error_msg}",
        user_intent="创建提醒",
        action_executed="create",
        intent_fulfilled=False,
        details={
            "error": "frequency_too_high",
            "recurrence_interval": recurrence_interval,
        },
    )
    return {"ok": False, "error": error_msg}


def _parse_and_validate_time(
    trigger_time: str, base_timestamp: Optional[int]
) -> tuple[Optional[int], Optional[dict]]:
    """
    解析并验证触发时间.

    Returns:
        (timestamp, error_response)-成功时 error_response 为 None
    """
    from datetime import datetime

    current_time = int(time.time())

    # 判断是否为相对时间
    is_relative = any(
        k in trigger_time for k in ["分钟后", "小时后", "天后", "明天", "后天", "下周"]
    )

    # 相对时间使用当前时间，绝对时间使用 base_timestamp
    timestamp = _parse_trigger_time(
        trigger_time, current_time if is_relative else base_timestamp
    )

    if not timestamp:
        semantic_message = (
            f"提醒创建失败：无法解析时间「{trigger_time}」，"
            "请使用格式如 '30分钟后' 或 '2025年12月09日15时00分'"
        )
        _save_reminder_result_to_session(
            semantic_message,
            user_intent="创建提醒",
            action_executed="create",
            intent_fulfilled=False,
            details={"error": "time_parse_failed", "trigger_time": trigger_time},
        )
        return None, {
            "ok": False,
            "error": f"无法解析时间: {trigger_time}，请使用格式如 '30分钟后' 或 '2025年12月09日15时00分'",
        }

    if timestamp <= current_time:
        trigger_time_str = datetime.fromtimestamp(timestamp).strftime(
            "%Y年%m月%d日%H时%M分"
        )
        current_time_str = datetime.fromtimestamp(current_time).strftime("%H时%M分")
        semantic_message = (
            f"提醒创建失败：触发时间 {trigger_time_str} 已经过去"
            f"（当前时间 {current_time_str}），请用户设置一个未来的时间"
        )
        _save_reminder_result_to_session(
            semantic_message,
            user_intent="创建提醒",
            action_executed="create",
            intent_fulfilled=False,
            details={"error": "time_in_past", "trigger_time": trigger_time_str},
        )
        return None, {
            "ok": False,
            "error": f"触发时间 {trigger_time_str} 已经过去（当前时间 {current_time_str}），请设置一个未来的时间",
            "suggestion": "请使用更长的相对时间（如'5分钟后'）或使用绝对时间格式",
        }

    return timestamp, None


def _check_duplicate_reminder(
    reminder_dao: ReminderDAO,
    user_id: str,
    title: str,
    timestamp: int,
    recurrence_type: str,
) -> Optional[dict]:
    """
    检查是否存在完全相同的提醒.

    Returns:
        如果存在重复返回 duplicate 响应，否则返回 None
    """
    from datetime import datetime

    existing = reminder_dao.find_similar_reminder(
        user_id=user_id,
        title=title,
        trigger_time=timestamp,
        recurrence_type=recurrence_type,
        time_tolerance=_TIME_TOLERANCE,
    )

    if not existing:
        return None

    existing_id = existing.get("reminder_id", "")
    existing_time = existing.get("next_trigger_time", 0)
    existing_time_str = (
        datetime.fromtimestamp(existing_time).strftime("%Y年%m月%d日%H时%M分")
        if existing_time
        else ""
    )

    logger.info(
        f"Duplicate reminder detected: title={title}, existing_id={existing_id}"
    )

    semantic_message = f"创建提醒成功：已为用户设置「{title}」提醒，时间为{existing_time_str}"
    _save_reminder_result_to_session(
        semantic_message,
        user_intent="创建提醒",
        action_executed="create",
        intent_fulfilled=True,
        details={"status": "duplicate", "existing_id": existing_id, "title": title},
    )

    return {
        "ok": True,
        "status": "duplicate",
        "reminder_id": existing_id,
        "duplicate": True,
        "message": f"已为用户设置「{title}」提醒，时间为{existing_time_str}",
    }


def _parse_time_period_config(
    period_start: Optional[str], period_end: Optional[str], period_days: Optional[str]
) -> Optional[dict]:
    """解析时间段配置."""
    if not (period_start and period_end):
        if period_start or period_end:
            logger.warning(
                f"Incomplete time period config: start={period_start}, end={period_end}"
            )
        return None

    active_days = None
    if period_days:
        try:
            active_days = [int(d.strip()) for d in period_days.split(",")]
        except (ValueError, AttributeError):
            logger.warning(f"Failed to parse period_days: {period_days}")

    config = {
        "enabled": True,
        "start_time": period_start,
        "end_time": period_end,
        "active_days": active_days,
        "timezone": "Asia/Shanghai",
    }
    logger.info(f"Time period config: {config}")
    return config


def _build_reminder_document(
    user_id: str,
    title: str,
    trigger_time: str,
    timestamp: int,
    action_template: Optional[str],
    recurrence_type: str,
    recurrence_interval: int,
    conversation_id: Optional[str],
    character_id: Optional[str],
    time_period_config: Optional[dict],
) -> dict:
    """构建提醒文档."""
    current_time = int(time.time())
    reminder_id = str(uuid.uuid4())

    reminder_doc = {
        "user_id": user_id,
        "reminder_id": reminder_id,
        "title": title,
        "action_template": action_template or f"记得{title}",
        "next_trigger_time": timestamp,
        "time_original": trigger_time,
        "timezone": "Asia/Shanghai",
        "recurrence": {
            "enabled": recurrence_type != "none",
            "type": recurrence_type if recurrence_type != "none" else None,
            "interval": recurrence_interval,
        },
        "status": "active",  # 阶段二状态重构：confirmed -> active
        "created_at": current_time,
        "updated_at": current_time,
        "triggered_count": 0,
    }

    # 设置默认次数上限（非时间段的周期提醒）
    if recurrence_type != "none" and not time_period_config:
        reminder_doc["recurrence"]["max_count"] = _DEFAULT_MAX_TRIGGERS
        logger.info(
            f"Set default max_count={_DEFAULT_MAX_TRIGGERS} for recurring reminder"
        )

    # 添加时间段配置
    if time_period_config:
        reminder_doc["time_period"] = time_period_config
        reminder_doc["period_state"] = {
            "today_first_trigger": None,
            "today_last_trigger": None,
            "today_trigger_count": 0,
        }

    # 添加可选字段
    if conversation_id:
        reminder_doc["conversation_id"] = conversation_id
    if character_id:
        reminder_doc["character_id"] = character_id

    return reminder_doc


def _format_success_message(
    title: str,
    timestamp: int,
    recurrence_type: str,
    recurrence_interval: int,
    reminder_doc: dict,
    time_period_config: Optional[dict],
) -> str:
    """格式化创建成功的语义化消息."""
    from datetime import datetime

    trigger_time_str = datetime.fromtimestamp(timestamp).strftime(
        "%Y年%m月%d日%H时%M分"
    )

    # 周期描述
    recurrence_desc = ""
    max_count_desc = ""
    if recurrence_type != "none":
        recurrence_map = {
            "daily": "每天",
            "weekly": "每周",
            "monthly": "每月",
            "yearly": "每年",
            "hourly": "每小时",
            "interval": f"每{recurrence_interval}分钟",
        }
        recurrence_desc = (
            f"，周期：{recurrence_map.get(recurrence_type, recurrence_type)}"
        )
        if reminder_doc["recurrence"].get("max_count"):
            max_count_desc = f"（最多提醒{reminder_doc['recurrence']['max_count']}次）"

    # 时间段描述
    period_desc = ""
    if time_period_config:
        days_map = {
            1: "周一",
            2: "周二",
            3: "周三",
            4: "周四",
            5: "周五",
            6: "周六",
            7: "周日",
        }
        active_days = time_period_config.get("active_days")
        if active_days == [1, 2, 3, 4, 5]:
            days_str = "工作日"
        elif active_days:
            days_str = "、".join([days_map[d] for d in active_days])
        else:
            days_str = "每天"
        period_desc = f"，时间段：{days_str} {time_period_config['start_time']}-{time_period_config['end_time']}"

    return (
        f"系统动作(非用户消息)：已按照用户最新的要求创建提醒成功：已为用户设置「{title}」提醒，"
        f"时间为{trigger_time_str}{recurrence_desc}{max_count_desc}{period_desc}"
    )


def _create_reminder(
    reminder_dao: ReminderDAO,
    user_id: str,
    title: Optional[str],
    trigger_time: Optional[str],
    action_template: Optional[str],
    recurrence_type: str,
    recurrence_interval: int,
    conversation_id: Optional[str],
    character_id: Optional[str],
    base_timestamp: Optional[int] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    period_days: Optional[str] = None,
) -> dict:
    """
     Create a new reminder with deduplication check.

     返回状态说明：
    -ok=True, status="created": 提醒创建成功
    -ok=True, status="duplicate": 已存在相同提醒
    -ok=True, status="needs_info": 信息不完整，需要用户补充（不写入数据库）
    -ok=False: 真正的错误（如时间解析失败、时间已过去等）

     重构说明：复杂度从 32 降低到约 12，通过提取辅助函数实现
    """
    from datetime import datetime

    # Step 1: 检查必要字段
    needs_info = _check_required_fields(title, trigger_time)
    if needs_info:
        return needs_info

    # GTD P0: 支持无时间任务 - 当 trigger_time 为 None 时，创建 inbox 任务
    if trigger_time is None:
        # 无时间任务：直接创建，不进行时间解析、去重检查等
        reminder_doc = _build_reminder_document(
            user_id=user_id,
            title=title,
            trigger_time=None,
            timestamp=None,
            action_template=action_template,
            recurrence_type="none",
            recurrence_interval=1,
            conversation_id=conversation_id,
            character_id=character_id,
            time_period_config=None,
        )
        reminder_id = reminder_doc["reminder_id"]

        try:
            inserted_id = reminder_dao.create_reminder(reminder_doc)
            if not inserted_id:
                _save_reminder_result_to_session(
                    "提醒创建失败：数据库写入失败，请稍后重试",
                    user_intent="创建提醒",
                    action_executed="create",
                    intent_fulfilled=False,
                )
                return {"ok": False, "error": "创建提醒失败"}

            logger.info(f"Inbox task created: id={reminder_id}, title={title}")

            semantic_message = f"系统动作(非用户消息)：已按照用户最新的要求创建任务成功：已为用户记录任务「{title}」（无时间，存入收集箱）"
            _save_reminder_result_to_session(
                semantic_message,
                user_intent="创建提醒",
                action_executed="create",
                intent_fulfilled=True,
                details={
                    "status": "created",
                    "reminder_id": reminder_id,
                    "title": title,
                    "trigger_time": None,
                    "list_id": "inbox",
                },
            )

            return {
                "ok": True,
                "status": "created",
                "reminder_id": reminder_id,
                "title": title,
                "trigger_time": None,
                "message": f"已创建任务「{title}」（无时间，存入收集箱）",
            }
        except Exception as e:
            logger.error(f"Error creating inbox task: {e}")
            return {"ok": False, "error": f"创建任务失败: {str(e)}"}

    # Step 2: 检查频率限制
    is_period_reminder = bool(period_start and period_end)
    freq_error = _check_frequency_limit(
        recurrence_type, recurrence_interval, is_period_reminder, user_id
    )
    if freq_error:
        return freq_error

    # Step 3: 解析并验证时间
    timestamp, time_error = _parse_and_validate_time(trigger_time, base_timestamp)
    if time_error:
        return time_error

    # Step 4: 去重检查-完全相同的提醒
    duplicate = _check_duplicate_reminder(
        reminder_dao, user_id, title, timestamp, recurrence_type
    )
    if duplicate:
        return duplicate



    # Step 5: 解析时间段配置
    time_period_config = _parse_time_period_config(
        period_start, period_end, period_days
    )

    # Step 6: 构建提醒文档
    reminder_doc = _build_reminder_document(
        user_id=user_id,
        title=title,
        trigger_time=trigger_time,
        timestamp=timestamp,
        action_template=action_template,
        recurrence_type=recurrence_type,
        recurrence_interval=recurrence_interval,
        conversation_id=conversation_id,
        character_id=character_id,
        time_period_config=time_period_config,
    )
    reminder_id = reminder_doc["reminder_id"]

    # Step 7: 创建提醒
    try:
        inserted_id = reminder_dao.create_reminder(reminder_doc)
        if not inserted_id:
            _save_reminder_result_to_session(
                "提醒创建失败：数据库写入失败，请稍后重试",
                user_intent="创建提醒",
                action_executed="create",
                intent_fulfilled=False,
            )
            return {"ok": False, "error": "创建提醒失败"}

        trigger_time_str = datetime.fromtimestamp(timestamp).strftime(
            "%Y年%m月%d日%H时%M分"
        )
        logger.info(
            f"Reminder created: id={reminder_id}, title={title}, time={trigger_time_str}"
        )

        # 构建成功消息
        semantic_message = _format_success_message(
            title,
            timestamp,
            recurrence_type,
            recurrence_interval,
            reminder_doc,
            time_period_config,
        )
        _save_reminder_result_to_session(
            semantic_message,
            user_intent="创建提醒",
            action_executed="create",
            intent_fulfilled=True,
            details={
                "status": "created",
                "reminder_id": reminder_id,
                "title": title,
                "trigger_time": trigger_time_str,
                "recurrence_type": recurrence_type,
                "max_count": reminder_doc["recurrence"].get("max_count"),
            },
        )

        # 标记本轮已创建定时提醒，防止 FutureResponse 重复设置
        current_session = _get_current_session_state()
        if current_session:
            current_session["reminder_created_with_time"] = True
            logger.debug("已设置 reminder_created_with_time=True")

        # 构建周期和时间段描述
        recurrence_desc = ""
        period_desc = ""
        if recurrence_type != "none":
            recurrence_map = {
                "daily": "每天",
                "weekly": "每周",
                "monthly": "每月",
                "yearly": "每年",
                "hourly": "每小时",
                "interval": f"每{recurrence_interval}分钟",
            }
            recurrence_desc = (
                f"，周期：{recurrence_map.get(recurrence_type, recurrence_type)}"
            )

        if time_period_config:
            days_map = {
                1: "周一",
                2: "周二",
                3: "周三",
                4: "周四",
                5: "周五",
                6: "周六",
                7: "周日",
            }
            active_days = time_period_config.get("active_days")
            if active_days == [1, 2, 3, 4, 5]:
                days_str = "工作日"
            elif active_days:
                days_str = "、".join([days_map[d] for d in active_days])
            else:
                days_str = "每天"
            period_desc = f"，时间段：{days_str} {time_period_config['start_time']}-{time_period_config['end_time']}"

        return {
            "ok": True,
            "status": "created",
            "reminder_id": reminder_id,
            "title": title,
            "trigger_time": trigger_time_str,
            "message": f"已创建提醒「{title}」，时间: {trigger_time_str}{recurrence_desc}{period_desc}",
        }

    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        _save_reminder_result_to_session(
            f"提醒创建失败：{str(e)}",
            user_intent="创建提醒",
            action_executed="create",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}


def _batch_create_reminders(
    reminder_dao: ReminderDAO,
    user_id: str,
    reminders_json: Optional[str],
    conversation_id: Optional[str],
    character_id: Optional[str],
    base_timestamp: Optional[int] = None,
) -> dict:
    """
    批量创建多个提醒，一次调用完成所有创建.

    Args:
        reminder_dao: ReminderDAO 实例
        user_id: 用户ID
        reminders_json: JSON字符串，包含提醒列表
        conversation_id: 会话ID
        character_id: 角色ID
        base_timestamp: 基准时间戳

    Returns:
        批量创建结果
    """
    import json
    from datetime import datetime

    if not reminders_json:
        _save_reminder_result_to_session("批量创建失败：未提供提醒列表")
        return {"ok": False, "error": "批量创建需要提供 reminders 参数"}

    # 解析 JSON
    try:
        reminders_list = json.loads(reminders_json)
        if not isinstance(reminders_list, list):
            raise ValueError("reminders 必须是数组")
    except (json.JSONDecodeError, ValueError) as e:
        _save_reminder_result_to_session(f"批量创建失败：JSON解析错误-{str(e)}")
        return {"ok": False, "error": f"reminders 参数格式错误: {str(e)}"}

    if not reminders_list:
        _save_reminder_result_to_session("批量创建失败：提醒列表为空")
        return {"ok": False, "error": "提醒列表不能为空"}

    # 限制批量创建数量，防止滥用
    MAX_BATCH_SIZE = 20
    if len(reminders_list) > MAX_BATCH_SIZE:
        _save_reminder_result_to_session(
            f"批量创建失败：一次最多创建{MAX_BATCH_SIZE}个提醒，当前请求{len(reminders_list)}个"
        )
        return {"ok": False, "error": f"一次最多创建{MAX_BATCH_SIZE}个提醒"}

    current_time = int(time.time())
    created_reminders = []
    failed_reminders = []

    for i, reminder_data in enumerate(reminders_list):
        title = reminder_data.get("title")
        trigger_time = reminder_data.get("trigger_time")
        recurrence_type = reminder_data.get("recurrence_type", "none")
        recurrence_interval = reminder_data.get("recurrence_interval", 1)

        # 验证必要字段
        if not title or not trigger_time:
            failed_reminders.append(
                {
                    "index": i,
                    "title": title or "(未指定)",
                    "error": "缺少 title 或 trigger_time",
                }
            )
            continue

        # 解析时间
        is_relative_time = any(
            keyword in trigger_time
            for keyword in ["分钟后", "小时后", "天后", "明天", "后天", "下周"]
        )
        if is_relative_time:
            timestamp = _parse_trigger_time(trigger_time, current_time)
        else:
            timestamp = _parse_trigger_time(trigger_time, base_timestamp)

        if not timestamp:
            failed_reminders.append(
                {"index": i, "title": title, "error": f"无法解析时间: {trigger_time}"}
            )
            continue

        # 验证时间在未来
        if timestamp <= current_time:
            trigger_time_str = datetime.fromtimestamp(timestamp).strftime(
                "%Y年%m月%d日%H时%M分"
            )
            failed_reminders.append(
                {"index": i, "title": title, "error": f"时间已过去: {trigger_time_str}"}
            )
            continue

        # 去重检查
        existing = reminder_dao.find_similar_reminder(
            user_id=user_id,
            title=title,
            trigger_time=timestamp,
            recurrence_type=recurrence_type,
            time_tolerance=300,
        )

        if existing:
            existing_time = existing.get("next_trigger_time", 0)
            existing_time_str = (
                datetime.fromtimestamp(existing_time).strftime("%Y年%m月%d日%H时%M分")
                if existing_time
                else ""
            )
            created_reminders.append(
                {
                    "title": title,
                    "trigger_time": existing_time_str,
                    "status": "duplicate",
                    "message": "已存在相同提醒",
                }
            )
            continue

        # 创建提醒
        reminder_id = str(uuid.uuid4())
        reminder_doc = {
            "user_id": user_id,
            "reminder_id": reminder_id,
            "title": title,
            "action_template": f"记得{title}",
            "next_trigger_time": timestamp,
            "time_original": trigger_time,
            "timezone": "Asia/Shanghai",
            "recurrence": {
                "enabled": recurrence_type != "none",
                "type": recurrence_type if recurrence_type != "none" else None,
                "interval": recurrence_interval,
            },
            "status": "active",  # 阶段二状态重构：confirmed -> active
            "created_at": current_time,
            "updated_at": current_time,
            "triggered_count": 0,
        }

        if conversation_id:
            reminder_doc["conversation_id"] = conversation_id
        if character_id:
            reminder_doc["character_id"] = character_id

        try:
            inserted_id = reminder_dao.create_reminder(reminder_doc)
            if inserted_id:
                trigger_time_str = datetime.fromtimestamp(timestamp).strftime(
                    "%Y年%m月%d日%H时%M分"
                )
                created_reminders.append(
                    {
                        "reminder_id": reminder_id,
                        "title": title,
                        "trigger_time": trigger_time_str,
                        "status": "created",
                    }
                )
                logger.info(
                    f"Batch created reminder: id={reminder_id}, title={title}, time={trigger_time_str}"
                )
            else:
                failed_reminders.append(
                    {"index": i, "title": title, "error": "数据库写入失败"}
                )
        except Exception as e:
            failed_reminders.append({"index": i, "title": title, "error": str(e)})

    # 构建语义化消息
    if created_reminders:
        success_list = [
            f"「{r['title']}」({r['trigger_time']})"
            for r in created_reminders
            if r.get("status") == "created"
        ]
        duplicate_list = [
            f"「{r['title']}」(已存在)"
            for r in created_reminders
            if r.get("status") == "duplicate"
        ]

        msg_parts = []
        if success_list:
            msg_parts.append(
                f"成功创建{len(success_list)}个提醒：{', '.join(success_list)}"
            )
        if duplicate_list:
            msg_parts.append(
                f"跳过{len(duplicate_list)}个重复提醒：{', '.join(duplicate_list)}"
            )
        if failed_reminders:
            fail_list = [f"「{r['title']}」({r['error']})" for r in failed_reminders]
            msg_parts.append(f"失败{len(failed_reminders)}个：{', '.join(fail_list)}")

        semantic_message = f"批量创建提醒结果：{'；'.join(msg_parts)}"
    else:
        semantic_message = f"批量创建失败：所有{len(failed_reminders)}个提醒都未能创建"

    _save_reminder_result_to_session(semantic_message)

    # V2.11 新增：如果有成功创建的提醒，设置标志防止 FutureResponse 重复设置
    if created_reminders and any(
        r.get("status") == "created" for r in created_reminders
    ):
        current_session = _get_current_session_state()
        if current_session:
            current_session["reminder_created_with_time"] = True
            logger.debug(
                "批量创建：已设置 reminder_created_with_time=True，防止 FutureResponse 重复设置"
            )

    return {
        "ok": len(created_reminders) > 0,
        "created": created_reminders,
        "failed": failed_reminders,
        "summary": {
            "total": len(reminders_list),
            "created": len(
                [r for r in created_reminders if r.get("status") == "created"]
            ),
            "duplicate": len(
                [r for r in created_reminders if r.get("status") == "duplicate"]
            ),
            "failed": len(failed_reminders),
        },
        "message": semantic_message,
    }


class _BatchOperationContext:
    """批量操作上下文，封装共享状态和配置"""

    # 常量配置
    MAX_BATCH_SIZE = 20
    MIN_INTERVAL_INFINITE = 60  # 无限重复提醒最小间隔：60分钟
    MIN_INTERVAL_PERIOD = 25  # 时间段提醒最小间隔：25分钟
    DEFAULT_MAX_TRIGGERS = 10
    TIME_TOLERANCE = 180  # 去重时间容差（秒），与 _TIME_TOLERANCE 保持一致

    def __init__(
        self,
        reminder_dao: ReminderDAO,
        user_id: str,
        conversation_id: Optional[str],
        character_id: Optional[str],
        base_timestamp: Optional[int],
    ):
        self.reminder_dao = reminder_dao
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.character_id = character_id
        self.base_timestamp = base_timestamp
        self.current_time = int(time.time())


def _parse_operations_json(operations_json: Optional[str]) -> tuple[bool, list | str]:
    """
    解析并验证操作列表 JSON.

    Returns:
        (success, operations_list | error_message)
    """
    import json

    if not operations_json:
        return False, "批量操作需要提供 operations 参数"

    try:
        operations_list = json.loads(operations_json)
        if not isinstance(operations_list, list):
            return False, "operations 必须是数组"
        if not operations_list:
            return False, "操作列表不能为空"
        if len(operations_list) > _BatchOperationContext.MAX_BATCH_SIZE:
            return (
                False,
                f"一次最多执行{_BatchOperationContext.MAX_BATCH_SIZE}个操作",
            )
        return True, operations_list
    except json.JSONDecodeError as e:
        return False, f"operations 参数格式错误: {str(e)}"


def _batch_op_create(ctx: _BatchOperationContext, op: dict) -> dict:
    """
    批量操作：创建单个提醒.

    Args:
        ctx: 批量操作上下文
        op: 操作参数字典

    Returns:
        操作结果字典
    """
    from datetime import datetime

    title = op.get("title")
    trigger_time = op.get("trigger_time")
    recurrence_type = op.get("recurrence_type", "none")
    recurrence_interval = op.get("recurrence_interval", 1)

    # 验证必要字段
    if not title or not trigger_time:
        return {"ok": False, "error": "缺少 title 或 trigger_time"}

    # 解析时间
    is_relative = any(
        k in trigger_time for k in ["分钟后", "小时后", "天后", "明天", "后天", "下周"]
    )
    timestamp = _parse_trigger_time(
        trigger_time, ctx.current_time if is_relative else ctx.base_timestamp
    )

    if not timestamp:
        return {"ok": False, "error": f"无法解析时间: {trigger_time}"}

    if timestamp <= ctx.current_time:
        return {"ok": False, "error": "时间已过去"}

    # 频率限制检查
    period_start = op.get("period_start")
    period_end = op.get("period_end")
    is_period_reminder = bool(period_start and period_end)

    if recurrence_type == "interval":
        if is_period_reminder and recurrence_interval < ctx.MIN_INTERVAL_PERIOD:
            logger.warning(
                f"Batch rejected period reminder: interval={recurrence_interval}min"
            )
            return {
                "ok": False,
                "error": f"频率过高：时间段提醒间隔不能少于{ctx.MIN_INTERVAL_PERIOD}分钟",
            }
        if not is_period_reminder and recurrence_interval < ctx.MIN_INTERVAL_INFINITE:
            logger.warning(
                f"Batch rejected infinite reminder: interval={recurrence_interval}min"
            )
            return {
                "ok": False,
                "error": f"频率过高：不支持每{recurrence_interval}分钟的无限重复提醒",
            }

    # 去重检查：完全相同的提醒
    existing = ctx.reminder_dao.find_similar_reminder(
        ctx.user_id, title, timestamp, recurrence_type, ctx.TIME_TOLERANCE
    )
    if existing:
        return {"ok": True, "status": "duplicate", "title": title}

    # 创建提醒
    return _do_create_reminder(
        ctx,
        title,
        trigger_time,
        timestamp,
        recurrence_type,
        recurrence_interval,
        is_period_reminder,
    )


def _do_create_reminder(
    ctx: _BatchOperationContext,
    title: str,
    trigger_time: str,
    timestamp: int,
    recurrence_type: str,
    recurrence_interval: int,
    is_period_reminder: bool,
) -> dict:
    """执行提醒创建"""
    from datetime import datetime

    reminder_id = str(uuid.uuid4())
    reminder_doc = {
        "user_id": ctx.user_id,
        "reminder_id": reminder_id,
        "title": title,
        "action_template": f"记得{title}",
        "next_trigger_time": timestamp,
        "time_original": trigger_time,
        "timezone": "Asia/Shanghai",
        "recurrence": {
            "enabled": recurrence_type != "none",
            "type": recurrence_type if recurrence_type != "none" else None,
            "interval": recurrence_interval,
        },
        "status": "active",  # 阶段二状态重构：confirmed -> active
        "created_at": ctx.current_time,
        "updated_at": ctx.current_time,
        "triggered_count": 0,
    }

    # 设置默认次数上限
    if recurrence_type != "none" and not is_period_reminder:
        reminder_doc["recurrence"]["max_count"] = ctx.DEFAULT_MAX_TRIGGERS

    if ctx.conversation_id:
        reminder_doc["conversation_id"] = ctx.conversation_id
    if ctx.character_id:
        reminder_doc["character_id"] = ctx.character_id

    try:
        if ctx.reminder_dao.create_reminder(reminder_doc):
            trigger_time_str = datetime.fromtimestamp(timestamp).strftime(
                "%Y年%m月%d日%H时%M分"
            )
            return {
                "ok": True,
                "status": "created",
                "title": title,
                "trigger_time": trigger_time_str,
                "reminder_id": reminder_id,
            }
        return {"ok": False, "error": "数据库写入失败"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _batch_op_update(ctx: _BatchOperationContext, op: dict) -> dict:
    """批量操作：按关键字更新提醒"""
    keyword = op.get("keyword")
    if not keyword or not keyword.strip():
        return {"ok": False, "error": "缺少 keyword（要修改的提醒关键字）"}

    keyword = keyword.strip()

    # 构建更新字段
    update_fields = {}
    if op.get("new_title"):
        update_fields["title"] = op["new_title"]
        update_fields["action_template"] = f"记得{op['new_title']}"
    if op.get("new_trigger_time"):
        ts = _parse_trigger_time(op["new_trigger_time"])
        if ts:
            update_fields["next_trigger_time"] = ts
            update_fields["time_original"] = op["new_trigger_time"]
        else:
            return {"ok": False, "error": f"无法解析时间: {op['new_trigger_time']}"}

    if not update_fields:
        return {
            "ok": False,
            "error": "没有要更新的字段（需要 new_title 或 new_trigger_time）",
        }

    try:
        updated_count, updated_reminders = ctx.reminder_dao.update_reminders_by_keyword(
            ctx.user_id, keyword, update_fields
        )
        if updated_count > 0:
            updated_titles = [r.get("title", "") for r in updated_reminders]
            return {
                "ok": True,
                "status": "updated",
                "keyword": keyword,
                "updated_count": updated_count,
                "updated_titles": updated_titles,
            }
        return {"ok": False, "error": f"没有找到包含「{keyword}」的提醒"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _batch_op_delete(ctx: _BatchOperationContext, op: dict) -> dict:
    """批量操作：按关键字删除提醒"""
    keyword = op.get("keyword")
    if not keyword or not keyword.strip():
        return {"ok": False, "error": "缺少 keyword（要删除的提醒关键字）"}

    keyword = keyword.strip()

    guard = _guard_side_effect_action(
        action="delete",
        reminder_dao=ctx.reminder_dao,
        user_id=ctx.user_id,
        keyword=keyword,
        session_state=_get_current_session_state(),
    )
    if not guard.get("allowed"):
        return {
            "ok": False,
            "error": guard.get("error"),
            "needs_confirmation": bool(guard.get("needs_confirmation")),
            "candidates": guard.get("candidates") or [],
        }
    if guard.get("resolved_keyword") is not None:
        keyword = guard.get("resolved_keyword")

    # 支持 "*" 删除所有
    if keyword == "*":
        try:
            deleted_count = ctx.reminder_dao.delete_all_by_user(ctx.user_id)
            return {
                "ok": True,
                "status": "deleted_all",
                "deleted_count": deleted_count,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    try:
        deleted_count, deleted_reminders = ctx.reminder_dao.delete_reminders_by_keyword(
            ctx.user_id, keyword
        )
        if deleted_count > 0:
            deleted_titles = [r.get("title", "") for r in deleted_reminders]
            return {
                "ok": True,
                "status": "deleted",
                "keyword": keyword,
                "deleted_count": deleted_count,
                "deleted_titles": deleted_titles,
            }
        return {"ok": False, "error": f"没有找到包含「{keyword}」的提醒"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _batch_op_complete(ctx: _BatchOperationContext, op: dict) -> dict:
    """批量操作：按关键字完成提醒"""
    keyword = op.get("keyword")
    if not keyword or not keyword.strip():
        return {"ok": False, "error": "缺少 keyword（要完成的提醒关键字）"}

    keyword = keyword.strip()

    guard = _guard_side_effect_action(
        action="complete",
        reminder_dao=ctx.reminder_dao,
        user_id=ctx.user_id,
        keyword=keyword,
        session_state=_get_current_session_state(),
    )
    if not guard.get("allowed"):
        return {
            "ok": False,
            "error": guard.get("error"),
            "needs_confirmation": bool(guard.get("needs_confirmation")),
            "candidates": guard.get("candidates") or [],
        }
    if guard.get("resolved_keyword") is not None:
        keyword = guard.get("resolved_keyword")

    try:
        completed_count, completed_reminders = (
            ctx.reminder_dao.complete_reminders_by_keyword(ctx.user_id, keyword)
        )
        if completed_count > 0:
            completed_titles = [r.get("title", "") for r in completed_reminders]
            return {
                "ok": True,
                "status": "completed",
                "keyword": keyword,
                "completed_count": completed_count,
                "completed_titles": completed_titles,
            }

        # 检查是否有已完成的提醒
        import re

        safe_keyword = re.escape(keyword)
        already_completed = list(
            ctx.reminder_dao.collection.find(
                {
                    "user_id": ctx.user_id,
                    "status": "completed",
                    "title": {"$regex": safe_keyword, "$options": "i"},
                }
            ).limit(5)
        )

        if already_completed:
            # 找到已完成的提醒，返回成功
            completed_titles = [r.get("title", "") for r in already_completed]
            return {
                "ok": True,
                "status": "already_completed",
                "keyword": keyword,
                "completed_count": 0,
                "already_completed_count": len(already_completed),
                "already_completed_titles": completed_titles,
            }

        return {"ok": False, "error": f"没有找到包含「{keyword}」的提醒"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# 操作处理器映射表
_BATCH_OP_HANDLERS = {
    "create": _batch_op_create,
    "update": _batch_op_update,
    "delete": _batch_op_delete,
    "complete": _batch_op_complete,
}


def _execute_batch_operations(
    ctx: _BatchOperationContext, operations_list: list
) -> tuple[list, int]:
    """
    执行批量操作列表.

    Returns:
        (results, success_count)
    """
    results = []
    success_count = 0

    for i, op in enumerate(operations_list):
        op_action = op.get("action")
        op_result = {"index": i, "action": op_action}

        handler = _BATCH_OP_HANDLERS.get(op_action)
        if handler:
            result = handler(ctx, op)
            op_result.update(result)
            if result.get("ok"):
                success_count += 1
        else:
            op_result["ok"] = False
            op_result["error"] = f"不支持的操作类型: {op_action}"

        results.append(op_result)

    return results, success_count


def _build_batch_summary(results: list) -> dict:
    """构建批量操作结果摘要"""
    created = [r for r in results if r.get("status") == "created"]
    appended = [r for r in results if r.get("status") == "appended"]
    duplicate = [r for r in results if r.get("status") == "duplicate"]
    updated = [r for r in results if r.get("status") == "updated"]
    deleted = [r for r in results if r.get("status") == "deleted"]
    completed = [r for r in results if r.get("status") == "completed"]
    already_completed = [r for r in results if r.get("status") == "already_completed"]
    failed = [r for r in results if not r.get("ok")]

    return {
        "created": created,
        "appended": appended,
        "duplicate": duplicate,
        "updated": updated,
        "deleted": deleted,
        "completed": completed,
        "already_completed": already_completed,
        "failed": failed,
    }


def _build_batch_message(summary: dict) -> str:
    """构建批量操作语义化消息"""
    msg_parts = []
    if summary["created"]:
        msg_parts.append(f"创建{len(summary['created'])}个提醒")
    if summary["appended"]:
        msg_parts.append(f"追加{len(summary['appended'])}个提醒")
    if summary["duplicate"]:
        msg_parts.append(f"跳过{len(summary['duplicate'])}个重复提醒")
    if summary["updated"]:
        msg_parts.append(f"更新{len(summary['updated'])}个提醒")
    if summary["deleted"]:
        msg_parts.append(f"删除{len(summary['deleted'])}个提醒")
    if summary.get("completed"):
        msg_parts.append(f"完成{len(summary['completed'])}个提醒")
    if summary.get("already_completed"):
        # 已完成的提醒也算成功，不显示为失败
        msg_parts.append(f"确认{len(summary['already_completed'])}个已完成的提醒")
    if summary["failed"]:
        msg_parts.append(f"失败{len(summary['failed'])}个")

    return f"批量操作完成：{'，'.join(msg_parts)}" if msg_parts else "批量操作完成"


def _batch_operations(
    reminder_dao: ReminderDAO,
    user_id: str,
    operations_json: Optional[str],
    conversation_id: Optional[str],
    character_id: Optional[str],
    base_timestamp: Optional[int] = None,
) -> dict:
    """
    批量执行多个操作（创建/更新/删除的任意组合）.

    Args:
        reminder_dao: ReminderDAO 实例
        user_id: 用户ID
        operations_json: JSON字符串，包含操作列表
        conversation_id: 会话ID
        character_id: 角色ID
        base_timestamp: 基准时间戳

    Returns:
        批量操作结果
    """
    # 解析并验证 JSON
    success, result = _parse_operations_json(operations_json)
    if not success:
        _save_reminder_result_to_session(f"批量操作失败：{result}")
        return {"ok": False, "error": result}

    operations_list = result

    # 创建操作上下文
    ctx = _BatchOperationContext(
        reminder_dao, user_id, conversation_id, character_id, base_timestamp
    )

    # 执行批量操作
    results, success_count = _execute_batch_operations(ctx, operations_list)

    # 构建摘要和消息
    summary = _build_batch_summary(results)
    semantic_message = _build_batch_message(summary)

    # 保存结果到 session
    # V2.12: intent_fulfilled 只有在没有失败时才为 True
    # V2.13: 如果有跳过的重复提醒，也视为意图未完全满足，模型需要告知用户
    # 如果有任何失败或重复，即使部分成功，也应该告知用户
    has_failures = len(summary["failed"]) > 0
    has_duplicates = len(summary["duplicate"]) > 0
    # 意图满足条件：有成功、无失败、无重复跳过
    intent_fulfilled = success_count > 0 and not has_failures and not has_duplicates
    _save_reminder_result_to_session(
        semantic_message,
        user_intent="批量操作提醒",
        action_executed="batch",
        intent_fulfilled=intent_fulfilled,
        details={
            "total": len(operations_list),
            "success": success_count,
            "created": len(summary["created"]),
            "appended": len(summary["appended"]),
            "duplicate": len(summary["duplicate"]),
            "updated": len(summary["updated"]),
            "deleted": len(summary["deleted"]),
            "completed": len(summary["completed"]),
            "failed": len(summary["failed"]),
        },
    )

    # 设置标志防止 FutureResponse 重复设置
    if summary["created"]:
        current_session = _get_current_session_state()
        if current_session:
            current_session["reminder_created_with_time"] = True
            logger.debug("批量操作：已设置 reminder_created_with_time=True")

    return {
        "ok": success_count > 0,
        "results": results,
        "summary": {
            "total": len(operations_list),
            "success": success_count,
            "created": len(summary["created"]),
            "appended": len(summary["appended"]),
            "duplicate": len(summary["duplicate"]),
            "updated": len(summary["updated"]),
            "deleted": len(summary["deleted"]),
            "completed": len(summary["completed"]),
            "failed": len(summary["failed"]),
        },
        "message": semantic_message,
    }


def _update_reminder_by_keyword(
    reminder_dao: ReminderDAO,
    user_id: str,
    keyword: Optional[str],
    new_title: Optional[str],
    new_trigger_time: Optional[str],
    recurrence_type: str = "none",
    recurrence_interval: int = 1,
) -> dict:
    """
    根据关键字更新提醒

    Args:
        reminder_dao: ReminderDAO 实例
        user_id: 用户ID
        keyword: 搜索关键字（必需）
        new_title: 新标题（可选）
        new_trigger_time: 新触发时间（可选）
        recurrence_type: 周期类型
        recurrence_interval: 周期间隔

    Returns:
        更新结果
    """
    if not user_id:
        _save_reminder_result_to_session(
            "提醒修改失败：无法获取用户信息",
            user_intent="修改提醒",
            action_executed="update",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": "修改提醒需要用户信息"}

    if not keyword or not keyword.strip():
        _save_reminder_result_to_session(
            "提醒修改失败：未指定要修改的提醒关键字",
            user_intent="修改提醒",
            action_executed="update",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": "更新操作需要提供 keyword（要修改的提醒关键字）"}

    keyword = keyword.strip()

    # 构建更新字段
    update_fields = {}
    update_desc = []

    if new_title:
        update_fields["title"] = new_title
        update_fields["action_template"] = f"记得{new_title}"
        update_desc.append(f"标题改为「{new_title}」")

    if new_trigger_time:
        timestamp = _parse_trigger_time(new_trigger_time)
        if timestamp:
            update_fields["next_trigger_time"] = timestamp
            update_fields["time_original"] = new_trigger_time
            from datetime import datetime

            time_str = datetime.fromtimestamp(timestamp).strftime(
                "%Y年%m月%d日%H时%M分"
            )
            update_desc.append(f"时间改为{time_str}")
        else:
            _save_reminder_result_to_session(
                f"提醒修改失败：无法解析时间「{new_trigger_time}」",
                user_intent="修改提醒",
                action_executed="update",
                intent_fulfilled=False,
            )
            return {"ok": False, "error": f"无法解析时间: {new_trigger_time}"}

    if recurrence_type and recurrence_type != "none":
        update_fields["recurrence"] = {
            "enabled": True,
            "type": recurrence_type,
            "interval": recurrence_interval,
        }
        recurrence_map = {
            "daily": "每天",
            "weekly": "每周",
            "monthly": "每月",
            "yearly": "每年",
            "interval": f"每{recurrence_interval}分钟",
        }
        update_desc.append(
            f"周期改为{recurrence_map.get(recurrence_type, recurrence_type)}"
        )

    if not update_fields:
        _save_reminder_result_to_session(
            "提醒修改失败：未提供要修改的内容（new_title 或 new_trigger_time）",
            user_intent="修改提醒",
            action_executed="update",
            intent_fulfilled=False,
        )
        return {
            "ok": False,
            "error": "没有提供要更新的字段（需要 new_title 或 new_trigger_time）",
        }

    try:
        updated_count, updated_reminders = reminder_dao.update_reminders_by_keyword(
            user_id, keyword, update_fields
        )

        if updated_count > 0:
            updated_titles = [r.get("title", "") for r in updated_reminders]
            titles_str = "、".join([f"「{t}」" for t in updated_titles[:5]])
            if len(updated_titles) > 5:
                titles_str += f" 等{len(updated_titles)}个"

            desc_str = "、".join(update_desc) if update_desc else "已更新"
            semantic_message = (
                f"提醒修改成功：已更新包含「{keyword}」的提醒 {titles_str}，{desc_str}"
            )
            _save_reminder_result_to_session(
                semantic_message,
                user_intent="修改提醒",
                action_executed="update",
                intent_fulfilled=True,
                details={
                    "keyword": keyword,
                    "updated_count": updated_count,
                    "updated_titles": updated_titles,
                    "updated_fields": list(update_fields.keys()),
                },
            )
            return {
                "ok": True,
                "updated_count": updated_count,
                "updated_reminders": updated_reminders,
                "message": semantic_message,
            }
        else:
            semantic_message = f"提醒修改失败：没有找到包含「{keyword}」的提醒"
            _save_reminder_result_to_session(
                semantic_message,
                user_intent="修改提醒",
                action_executed="update",
                intent_fulfilled=False,
                details={"keyword": keyword, "updated_count": 0},
            )
            return {
                "ok": False,
                "error": f"没有找到或已经完成了包含「{keyword}」的提醒",
                "updated_count": 0,
            }

    except Exception as e:
        logger.error(f"Failed to update reminders by keyword '{keyword}': {e}")
        _save_reminder_result_to_session(
            f"提醒修改失败：{str(e)}",
            user_intent="修改提醒",
            action_executed="update",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}


def _delete_reminder_by_keyword(
    reminder_dao: ReminderDAO, user_id: str, keyword: Optional[str]
) -> dict:
    """
    根据关键字删除提醒

    Args:
        reminder_dao: ReminderDAO 实例
        user_id: 用户ID
        keyword: 搜索关键字，使用 "*" 删除所有提醒

    Returns:
        删除结果
    """
    if not user_id:
        _save_reminder_result_to_session(
            "提醒删除失败：无法获取用户信息",
            user_intent="删除提醒",
            action_executed="delete",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": "删除提醒需要用户信息"}

    if not keyword or not keyword.strip():
        _save_reminder_result_to_session(
            "提醒删除失败：未指定要删除的提醒关键字",
            user_intent="删除提醒",
            action_executed="delete",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": "删除操作需要提供 keyword（要删除的提醒关键字）"}

    keyword = keyword.strip()

    # 支持 "*" 删除所有提醒
    if keyword == "*":
        try:
            deleted_count = reminder_dao.delete_all_by_user(user_id)
            if deleted_count > 0:
                semantic_message = (
                    f"提醒删除成功：已删除全部 {deleted_count} 个待办提醒"
                )
                _save_reminder_result_to_session(
                    semantic_message,
                    user_intent="删除所有提醒",
                    action_executed="delete_all",
                    intent_fulfilled=True,
                    details={"deleted_count": deleted_count},
                )
                return {
                    "ok": True,
                    "deleted_count": deleted_count,
                    "message": semantic_message,
                }
            else:
                semantic_message = "提醒删除完成：用户当前没有待办提醒"
                _save_reminder_result_to_session(
                    semantic_message,
                    user_intent="删除所有提醒",
                    action_executed="delete_all",
                    intent_fulfilled=True,
                    details={"deleted_count": 0},
                )
                return {"ok": True, "deleted_count": 0, "message": semantic_message}
        except Exception as e:
            logger.error(f"Failed to delete all reminders: {e}")
            _save_reminder_result_to_session(
                f"提醒删除失败：{str(e)}",
                user_intent="删除所有提醒",
                action_executed="delete_all",
                intent_fulfilled=False,
            )
            return {"ok": False, "error": str(e)}

    # 按关键字删除
    try:
        deleted_count, deleted_reminders = reminder_dao.delete_reminders_by_keyword(
            user_id, keyword
        )

        if deleted_count > 0:
            deleted_titles = [r.get("title", "") for r in deleted_reminders]
            titles_str = "、".join([f"「{t}」" for t in deleted_titles[:5]])
            if len(deleted_titles) > 5:
                titles_str += f" 等{len(deleted_titles)}个"

            semantic_message = (
                f"提醒删除成功：已删除包含「{keyword}」的提醒：{titles_str}"
            )
            _save_reminder_result_to_session(
                semantic_message,
                user_intent="删除提醒",
                action_executed="delete_by_keyword",
                intent_fulfilled=True,
                details={
                    "keyword": keyword,
                    "deleted_count": deleted_count,
                    "deleted_titles": deleted_titles,
                },
            )
            return {
                "ok": True,
                "deleted_count": deleted_count,
                "deleted_reminders": deleted_reminders,
                "message": semantic_message,
            }
        else:
            semantic_message = f"提醒删除失败：没有找到包含「{keyword}」的提醒"
            _save_reminder_result_to_session(
                semantic_message,
                user_intent="删除提醒",
                action_executed="delete_by_keyword",
                intent_fulfilled=False,
                details={"keyword": keyword, "deleted_count": 0},
            )
            return {
                "ok": False,
                "error": f"没有找到或已经完成了包含「{keyword}」的提醒",
                "deleted_count": 0,
            }

    except Exception as e:
        logger.error(f"Failed to delete reminders by keyword '{keyword}': {e}")
        _save_reminder_result_to_session(
            f"提醒删除失败：{str(e)}",
            user_intent="删除提醒",
            action_executed="delete_by_keyword",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}


def _format_time_with_date(timestamp: int) -> str:
    """
    格式化时间戳为带完整日期的友好格式

    Args:
        timestamp: Unix时间戳

    Returns:
        str: 完整日期时间，如 "12月30日 星期二 下午4点45分"
    """
    dt = datetime.fromtimestamp(timestamp)

    # 日期部分
    date_str = f"{dt.month}月{dt.day}日"

    # 星期部分
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_str = weekdays[dt.weekday()]

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

    return f"{date_str} {weekday_str} {time_str}"


def _get_status_indicator(status: str) -> str:
    """
    获取状态的友好指示符

    Args:
        status: 提醒状态

    Returns:
        str: 状态指示符，如 "✓已完成" / "⏳待执行"

    Note:
        阶段二状态重构：
        - active: 未完成（替代 confirmed/pending）
        - triggered: 已触发
        - completed: 已完成（替代 completed/cancelled）
    """
    status_map = {
        # 新状态系统（阶段二）
        "active": "⏳待执行",
        "triggered": "🔔已触发",
        "completed": "✓已完成",
        # 向后兼容旧状态
        "confirmed": "⏳待执行",
        "pending": "⏳待执行",
        "cancelled": "✗已取消",
    }
    return status_map.get(status, status)


def _list_reminders(
    reminder_dao: ReminderDAO, user_id: str, include_all: bool = False
) -> dict:
    """
    List reminders for a user.

    已废弃：请使用 _filter_reminders 替代

    Args:
        reminder_dao: ReminderDAO 实例
        user_id: 用户ID
        include_all: 是否包含所有状态的提醒，默认 False 只返回有效提醒
    """
    try:
        if include_all:
            # 查询所有状态的提醒
            reminders = reminder_dao.find_reminders_by_user(user_id)
        else:
            # 默认只查询有效状态的提醒（阶段二：active）
            reminders = reminder_dao.find_reminders_by_user(
                user_id, status_list=["active"]
            )

        # Format reminders for output
        formatted_reminders = []
        reminder_summaries = []
        for i, reminder in enumerate(reminders, 1):
            trigger_time = reminder.get("next_trigger_time", 0)
            status = reminder.get("status", "")

            formatted = {
                "reminder_id": reminder.get("reminder_id"),
                "title": reminder.get("title"),
                "status": status,
                "status_display": _get_status_indicator(status),
                "next_trigger_time": trigger_time,
                "time_friendly": (
                    format_time_friendly(trigger_time) if trigger_time else ""
                ),
                "time_with_date": (
                    _format_time_with_date(trigger_time) if trigger_time else ""
                ),
                "recurrence": reminder.get("recurrence", {}),
                "created_at": reminder.get("created_at"),
                "triggered_count": reminder.get("triggered_count", 0),
            }
            formatted_reminders.append(formatted)

            # 构建简洁的提醒摘要（包含完整日期和状态）
            title = reminder.get("title", "")
            time_with_date = formatted["time_with_date"] or "未设置时间"
            status_indicator = _get_status_indicator(status)
            reminder_summaries.append(
                f"{i}.{title}({time_with_date}) [{status_indicator}]"
            )

        # 语义化输出查询结果
        if formatted_reminders:
            summary_str = " ".join(reminder_summaries)
            semantic_message = (
                f"查询成功：用户当前有{len(formatted_reminders)}个提醒：{summary_str}"
            )
        else:
            semantic_message = "查询成功：用户当前没有待执行的提醒"
        _save_reminder_result_to_session(
            semantic_message,
            user_intent="查询提醒",
            action_executed="list",
            intent_fulfilled=True,
            details={
                "count": len(formatted_reminders),
                "reminders": formatted_reminders,
            },
        )

        return {"ok": True, "reminders": formatted_reminders}
    except Exception as e:
        logger.error(f"Failed to list reminders: {e}")
        _save_reminder_result_to_session(
            f"提醒查询失败：{str(e)}",
            user_intent="查询提醒",
            action_executed="list",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}


def _filter_reminders(
    reminder_dao: ReminderDAO,
    user_id: str,
    status: Optional[str] = None,
    reminder_type: Optional[str] = None,
    keyword: Optional[str] = None,
    trigger_after: Optional[str] = None,
    trigger_before: Optional[str] = None,
    base_timestamp: Optional[int] = None,
) -> dict:
    """
    灵活筛选用户的提醒（阶段二新增，替代 list）

    Args:
        reminder_dao: ReminderDAO 实例
        user_id: 用户ID
        status: 状态筛选，JSON字符串如 '["active", "triggered"]'，默认 ["active"]
        reminder_type: 提醒类型，"one_time" | "recurring"
        keyword: 关键字搜索，模糊匹配 title
        trigger_after: 时间范围开始，如 "今天00:00" 或 "2026年01月03日00时00分"
        trigger_before: 时间范围结束，如 "今天23:59" 或 "2026年01月03日23时59分"
        base_timestamp: 基准时间戳（用于相对时间计算）

    Returns:
        查询结果字典
    """
    import json

    try:
        # 解析状态参数
        status_list = None
        if status:
            try:
                status_list = json.loads(status)
                if not isinstance(status_list, list):
                    status_list = [status_list]
            except json.JSONDecodeError:
                # 如果不是 JSON，尝试作为单个状态处理
                status_list = [status]

        # 解析时间范围
        trigger_after_ts = None
        trigger_before_ts = None
        current_time = int(time.time())

        if trigger_after:
            trigger_after_ts = _parse_trigger_time(
                trigger_after, base_timestamp or current_time
            )
            if not trigger_after_ts:
                logger.warning(f"Failed to parse trigger_after: {trigger_after}")

        if trigger_before:
            trigger_before_ts = _parse_trigger_time(
                trigger_before, base_timestamp or current_time
            )
            if not trigger_before_ts:
                logger.warning(f"Failed to parse trigger_before: {trigger_before}")

        # 调用 DAO 层的 filter 方法
        reminders = reminder_dao.filter_reminders(
            user_id=user_id,
            status_list=status_list,
            reminder_type=reminder_type,
            keyword=keyword,
            trigger_after=trigger_after_ts,
            trigger_before=trigger_before_ts,
        )

        # 格式化输出
        formatted_reminders = []
        reminder_summaries = []
        for i, reminder in enumerate(reminders, 1):
            trigger_time = reminder.get("next_trigger_time", 0)
            reminder_status = reminder.get("status", "")

            formatted = {
                "reminder_id": reminder.get("reminder_id"),
                "title": reminder.get("title"),
                "status": reminder_status,
                "status_display": _get_status_indicator(reminder_status),
                "next_trigger_time": trigger_time,
                "time_friendly": (
                    format_time_friendly(trigger_time) if trigger_time else ""
                ),
                "time_with_date": (
                    _format_time_with_date(trigger_time) if trigger_time else ""
                ),
                "recurrence": reminder.get("recurrence", {}),
                "created_at": reminder.get("created_at"),
                "triggered_count": reminder.get("triggered_count", 0),
            }
            formatted_reminders.append(formatted)

            # 构建简洁的提醒摘要
            title = reminder.get("title", "")
            time_with_date = formatted["time_with_date"] or "未设置时间"
            status_indicator = _get_status_indicator(reminder_status)
            reminder_summaries.append(
                f"{i}.{title}({time_with_date}) [{status_indicator}]"
            )

        # 分组：有时间 vs 无时间
        reminders_with_time = [r for r in formatted_reminders if r.get("next_trigger_time")]
        reminders_inbox = [r for r in formatted_reminders if not r.get("next_trigger_time")]

        # 构建分组显示消息
        message_parts = []

        if reminders_with_time:
            message_parts.append("📅 定时提醒：")
            for r in reminders_with_time:
                title = r.get("title", "未命名")
                time_with_date = r.get("time_with_date", "")
                message_parts.append(f"  • {title} - {time_with_date}")

        if reminders_inbox:
            message_parts.append("\n📥 待安排（Inbox）：")
            for r in reminders_inbox:
                title = r.get("title", "未命名")
                message_parts.append(f"  • {title}")

        if not reminders_with_time and not reminders_inbox:
            final_message = "当前没有符合条件的提醒"
        else:
            final_message = "\n".join(message_parts)

        # 构建筛选条件描述（用于日志）
        filter_desc_parts = []
        if status_list:
            filter_desc_parts.append(f"状态={status_list}")
        if reminder_type:
            type_desc = "单次" if reminder_type == "one_time" else "周期"
            filter_desc_parts.append(f"类型={type_desc}")
        if keyword:
            filter_desc_parts.append(f"关键字={keyword}")
        if trigger_after:
            filter_desc_parts.append(f"从={trigger_after}")
        if trigger_before:
            filter_desc_parts.append(f"到={trigger_before}")
        filter_desc = "，".join(filter_desc_parts) if filter_desc_parts else "默认条件"

        # 语义化输出查询结果（保留旧格式用于session）
        if formatted_reminders:
            summary_str = " ".join(reminder_summaries)
            semantic_message = f"查询成功（{filter_desc}）：找到{len(formatted_reminders)}个提醒：{summary_str}"
        else:
            semantic_message = f"查询成功（{filter_desc}）：没有找到符合条件的提醒"

        _save_reminder_result_to_session(
            semantic_message,
            user_intent="筛选提醒",
            action_executed="filter",
            intent_fulfilled=True,
            details={
                "count": len(formatted_reminders),
                "filter": {
                    "status": status_list,
                    "reminder_type": reminder_type,
                    "keyword": keyword,
                    "trigger_after": trigger_after,
                    "trigger_before": trigger_before,
                },
                "reminders": formatted_reminders,
            },
        )

        return {
            "ok": True,
            "status": "success",
            "reminders": formatted_reminders,
            "count": len(formatted_reminders),
            "message": final_message,
        }

    except Exception as e:
        logger.error(f"Failed to filter reminders: {e}")
        _save_reminder_result_to_session(
            f"提醒筛选失败：{str(e)}",
            user_intent="筛选提醒",
            action_executed="filter",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}


def _complete_reminder(
    reminder_dao: ReminderDAO,
    user_id: str,
    keyword: Optional[str],
) -> dict:
    """
    根据关键字完成提醒（阶段二新增）

    Args:
        reminder_dao: ReminderDAO 实例
        user_id: 用户ID
        keyword: 搜索关键字（必需）

    Returns:
        完成结果字典
    """
    if not user_id:
        _save_reminder_result_to_session(
            "提醒完成失败：无法获取用户信息",
            user_intent="完成提醒",
            action_executed="complete",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": "完成提醒需要用户信息"}

    if not keyword or not keyword.strip():
        _save_reminder_result_to_session(
            "提醒完成失败：未指定要完成的提醒关键字",
            user_intent="完成提醒",
            action_executed="complete",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": "完成操作需要提供 keyword（要完成的提醒关键字）"}

    keyword = keyword.strip()

    try:
        completed_count, completed_reminders = (
            reminder_dao.complete_reminders_by_keyword(user_id, keyword)
        )

        if completed_count > 0:
            completed_titles = [r.get("title", "") for r in completed_reminders]
            titles_str = "、".join([f"「{t}」" for t in completed_titles[:5]])
            if len(completed_titles) > 5:
                titles_str += f" 等{len(completed_titles)}个"

            semantic_message = (
                f"提醒完成成功：已完成包含「{keyword}」的提醒：{titles_str}"
            )
            _save_reminder_result_to_session(
                semantic_message,
                user_intent="完成提醒",
                action_executed="complete",
                intent_fulfilled=True,
                details={
                    "keyword": keyword,
                    "completed_count": completed_count,
                    "completed_titles": completed_titles,
                },
            )
            return {
                "ok": True,
                "completed_count": completed_count,
                "completed_reminders": completed_reminders,
                "message": semantic_message,
            }
        else:
            # 检查是否有已完成的提醒（用户可能在确认已完成的任务）
            import re

            safe_keyword = re.escape(keyword)
            already_completed = list(
                reminder_dao.collection.find(
                    {
                        "user_id": user_id,
                        "status": "completed",
                        "title": {"$regex": safe_keyword, "$options": "i"},
                    }
                ).limit(5)
            )

            if already_completed:
                # 找到已完成的提醒，这是正常情况，不应报错
                completed_titles = [r.get("title", "") for r in already_completed]
                titles_str = "、".join([f"「{t}」" for t in completed_titles[:3]])
                if len(completed_titles) > 3:
                    titles_str += f" 等{len(completed_titles)}个"

                semantic_message = (
                    f"好的，包含「{keyword}」的提醒（{titles_str}）已经完成了"
                )
                _save_reminder_result_to_session(
                    semantic_message,
                    user_intent="完成提醒",
                    action_executed="complete",
                    intent_fulfilled=True,  # 标记为成功，因为提醒确实已完成
                    details={
                        "keyword": keyword,
                        "completed_count": 0,
                        "already_completed_count": len(already_completed),
                        "already_completed_titles": completed_titles,
                    },
                )
                return {
                    "ok": True,
                    "completed_count": 0,
                    "already_completed": True,
                    "message": semantic_message,
                }
            else:
                # 真的没有找到任何相关提醒
                semantic_message = f"没有找到包含「{keyword}」的提醒"
                _save_reminder_result_to_session(
                    semantic_message,
                    user_intent="完成提醒",
                    action_executed="complete",
                    intent_fulfilled=False,
                    details={"keyword": keyword, "completed_count": 0},
                )
                return {
                    "ok": False,
                    "error": f"没有找到包含「{keyword}」的提醒",
                    "completed_count": 0,
                }

    except Exception as e:
        logger.error(f"Failed to complete reminders by keyword '{keyword}': {e}")
        _save_reminder_result_to_session(
            f"提醒完成失败：{str(e)}",
            user_intent="完成提醒",
            action_executed="complete",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}
