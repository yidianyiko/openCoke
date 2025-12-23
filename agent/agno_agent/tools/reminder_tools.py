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

Fix: 使用线程本地存储 (Thread Local Storage) 解决多 Worker 并发时的跨用户数据污染问题
"""

import logging
import uuid
import time
import threading
from typing import Optional, Literal, Union
from agno.tools import tool

from dao.reminder_dao import ReminderDAO
from util.time_util import parse_relative_time, str2timestamp, format_time_friendly

logger = logging.getLogger(__name__)


def _parse_trigger_time(trigger_time: str, base_timestamp: Optional[int] = None) -> Optional[int]:
    """
    Parse trigger time from string to timestamp.
    
    Supports:
    - Relative time: "30分钟后", "2小时后", "明天", "后天", "下周"
    - Absolute time: "2024年12月25日09时00分"
    
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


# 使用线程本地存储，确保每个 Worker 线程有独立的 session_state
# 解决多 Worker 并发处理不同用户请求时的数据污染问题
_thread_local = threading.local()


def set_reminder_session_state(session_state: dict):
    """
    设置当前线程的会话状态，供 reminder_tool 使用
    
    使用线程本地存储确保不同 Worker 线程之间的 session_state 相互隔离，
    避免并发处理时的跨用户数据污染。
    """
    _thread_local.session_state = session_state or {}
    # 每次新会话重置操作记录
    _thread_local.session_operations = []
    
    # 记录设置的 user_id，便于调试
    user_id = str(session_state.get("user", {}).get("_id", "")) if session_state else ""
    logger.debug(f"set_reminder_session_state: thread={threading.current_thread().name}, user_id={user_id}")


def _get_current_session_state() -> dict:
    """获取当前线程的 session_state"""
    return getattr(_thread_local, 'session_state', {})


def _get_session_operations() -> list:
    """获取当前线程的操作记录"""
    if not hasattr(_thread_local, 'session_operations'):
        _thread_local.session_operations = []
    return _thread_local.session_operations


def _check_operation_allowed(action: str) -> tuple[bool, str]:
    """
    检查操作是否允许，防止循环调用
    
    规则：
    - batch 操作只能调用一次（内部可包含多种操作类型）
    - 单独的 create/update/delete/list 各只能调用一次
    - batch 之后不能再调用其他操作
    - 其他操作之后不能调用 batch
    
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


def _save_reminder_result_to_session(message: str):
    """
    将提醒操作结果保存到 session_state，供 ChatAgent 作为上下文使用
    
    Args:
        message: 语义化的操作结果描述
    """
    session_state = _get_current_session_state()
    session_state["【提醒设置工具消息】"] = message
    logger.info(f"提醒结果已写入 session_state: {message}")


@tool(description="""提醒管理工具，用于创建、更新、删除、查询提醒。支持单次提醒、周期提醒和时间段提醒。

## 操作类型 (action)
- "create": 创建单个提醒
- "batch": 批量操作（推荐），一次调用执行多个操作（创建/更新/删除的任意组合）
- "update": 更新单个提醒
- "delete": 删除单个提醒
- "list": 查询提醒列表

## 单个操作参数

### create 参数
- title: 提醒标题（必需），如"开会"、"喝水"
- trigger_time: 触发时间（必需），格式"xxxx年xx月xx日xx时xx分"或"30分钟后"
- recurrence_type: 周期类型，可选值: "none"(默认)、"daily"、"weekly"、"monthly"、"interval"
- recurrence_interval: 周期间隔数，默认1
- period_start/period_end: 时间段，格式 "HH:MM"
- period_days: 生效星期，格式 "1,2,3,4,5"

### update 参数
- reminder_id: 要更新的提醒ID（必需）
- title/trigger_time: 新值（可选）

### delete 参数
- reminder_id: 要删除的提醒ID（必需）

## 批量操作 (action="batch") - 推荐用于复杂场景

当用户消息包含多个操作时使用，一次调用完成所有操作。

参数:
- operations: JSON字符串，包含操作列表。每个操作包含 action 和对应参数。

格式:
```
[
  {"action": "delete", "reminder_id": "xxx"},
  {"action": "create", "title": "喝水", "trigger_time": "2025年12月24日15时00分"},
  {"action": "update", "reminder_id": "yyy", "title": "新标题"}
]
```

示例1："把开会提醒删掉，再帮我加一个喝水提醒"
→ action="batch", operations='[{"action":"delete","reminder_id":"xxx"},{"action":"create","title":"喝水","trigger_time":"..."}]'

示例2："帮我设置三个提醒：8点起床、12点吃饭、6点下班"
→ action="batch", operations='[{"action":"create","title":"起床","trigger_time":"..."},{"action":"create","title":"吃饭","trigger_time":"..."},{"action":"create","title":"下班","trigger_time":"..."}]'

示例3："删除提醒1，把提醒2改到明天，再加一个新提醒"
→ action="batch", operations='[{"action":"delete","reminder_id":"1"},{"action":"update","reminder_id":"2","trigger_time":"..."},{"action":"create","title":"...","trigger_time":"..."}]'

注意: 时间格式必须是"xxxx年xx月xx日xx时xx分"，不支持"下午3点"等格式。
""")
def reminder_tool(
    action: str,
    title: Optional[str] = None,
    trigger_time: Optional[str] = None,
    action_template: Optional[str] = None,
    reminder_id: Optional[str] = None,
    recurrence_type: str = "none",
    recurrence_interval: int = 1,
    # 时间段提醒参数
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    period_days: Optional[str] = None,
    # 批量操作参数
    operations: Optional[str] = None
) -> dict:
    """
    提醒管理统一工具
    
    Args:
        action: 操作类型 - "create"、"batch"、"update"、"delete"、"list"
        title: 提醒标题
        trigger_time: 触发时间
        action_template: 提醒文案模板（可选）
        reminder_id: 提醒ID（update/delete 时必填）
        recurrence_type: 周期类型，默认"none"
        recurrence_interval: 周期间隔数，默认1
        operations: 批量操作时的操作列表JSON字符串
    
    Returns:
        操作结果字典
    """
    # 获取当前线程的 session_state（线程安全）
    current_session_state = _get_current_session_state()
    
    # 修正 LLM 可能传递的嵌套参数格式问题
    if isinstance(action, dict) and 'action' in action:
        action = action['action']
    
    # 手动验证 action 值
    valid_actions = ("create", "batch", "update", "delete", "list")
    if action not in valid_actions:
        return {"ok": False, "error": f"不支持的操作类型: {action}，支持的操作: {valid_actions}"}
    
    # 检查操作组合是否允许（防止循环调用）
    allowed, error_msg = _check_operation_allowed(action)
    if not allowed:
        logger.warning(f"操作被拒绝: action={action}, reason={error_msg}")
        _save_reminder_result_to_session(f"操作被拒绝：{error_msg}")
        return {"ok": False, "error": error_msg}
    
    # 从线程本地 session_state 获取用户信息
    user_id = str(current_session_state.get("user", {}).get("_id", ""))
    character_id = str(current_session_state.get("character", {}).get("_id", ""))
    conversation_id = str(current_session_state.get("conversation", {}).get("_id", ""))
    
    if not user_id and action in ["create", "batch", "list"]:
        logger.warning(f"reminder_tool: user_id not found in session_state, thread={threading.current_thread().name}")
        return {"ok": False, "error": "无法获取用户信息，请稍后重试"}
    
    reminder_dao = ReminderDAO()
    
    logger.info(f"reminder_tool called: action={action}, title={title}, trigger_time={trigger_time}, user_id={user_id}")
    
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
                period_days=period_days
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
                base_timestamp=message_timestamp
            )
            logger.info(f"reminder_tool batch result: {result}")
            return result
        
        elif action == "update":
            return _update_reminder(
                reminder_dao=reminder_dao,
                reminder_id=reminder_id,
                title=title,
                trigger_time=trigger_time,
                action_template=action_template,
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval
            )
        
        elif action == "delete":
            return _delete_reminder(
                reminder_dao=reminder_dao,
                reminder_id=reminder_id
            )
        
        elif action == "list":
            return _list_reminders(
                reminder_dao=reminder_dao,
                user_id=user_id
            )
        
        else:
            return {"ok": False, "error": f"不支持的操作类型: {action}"}
    
    except Exception as e:
        logger.error(f"Error in reminder_tool: {e}")
        return {"ok": False, "error": str(e)}
    
    finally:
        reminder_dao.close()


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
    period_days: Optional[str] = None
) -> dict:
    """
    Create a new reminder with deduplication check.
    
    返回状态说明：
    - ok=True, status="created": 提醒创建成功
    - ok=True, status="duplicate": 已存在相同提醒
    - ok=True, status="needs_info": 信息不完整，需要用户补充（不写入数据库）
    - ok=False: 真正的错误（如时间解析失败、时间已过去等）
    """
    # ========== 信息完整性检查 ==========
    # 缺少必要信息时返回 needs_info 状态，不写入数据库
    missing_fields = []
    draft_info = {}
    
    if not title:
        missing_fields.append("title")
    else:
        draft_info["title"] = title
    
    if not trigger_time:
        missing_fields.append("trigger_time")
    else:
        draft_info["trigger_time"] = trigger_time
    
    if missing_fields:
        # 信息不完整，返回 needs_info 状态
        # 注意：这里 ok=True 表示这不是错误，只是需要更多信息
        logger.info(f"Reminder needs more info: missing={missing_fields}, draft={draft_info}")
        
        # 构建语义化消息
        missing_desc = "、".join(["提醒内容" if f == "title" else "提醒时间" for f in missing_fields])
        semantic_message = f"信息不足：用户想设置提醒，但缺少【{missing_desc}】，请询问用户补充"
        _save_reminder_result_to_session(semantic_message)
        
        return {
            "ok": True,
            "status": "needs_info",
            "missing_fields": missing_fields,
            "draft": draft_info,
            "message": _get_missing_info_prompt(missing_fields)
        }
    
    current_time = int(time.time())
    
    # 对于相对时间，始终使用当前时间作为基准，避免消息延迟导致的问题
    # 只有绝对时间才使用 base_timestamp
    is_relative_time = any(keyword in trigger_time for keyword in ['分钟后', '小时后', '天后', '明天', '后天', '下周'])
    
    if is_relative_time:
        # 相对时间：使用当前时间计算，确保提醒时间在未来
        timestamp = _parse_trigger_time(trigger_time, current_time)
    else:
        # 绝对时间：直接解析
        timestamp = _parse_trigger_time(trigger_time, base_timestamp)
    
    if not timestamp:
        semantic_message = f"提醒创建失败：无法解析时间「{trigger_time}」，请使用格式如 '30分钟后' 或 '2025年12月09日15时00分'"
        _save_reminder_result_to_session(semantic_message)
        return {"ok": False, "error": f"无法解析时间: {trigger_time}，请使用格式如 '30分钟后' 或 '2025年12月09日15时00分'"}
    
    # Validate timestamp is in the future
    if timestamp <= current_time:
        from datetime import datetime
        trigger_time_str = datetime.fromtimestamp(timestamp).strftime('%Y年%m月%d日%H时%M分')
        current_time_str = datetime.fromtimestamp(current_time).strftime('%H时%M分')
        semantic_message = f"提醒创建失败：触发时间 {trigger_time_str} 已经过去（当前时间 {current_time_str}），请用户设置一个未来的时间"
        _save_reminder_result_to_session(semantic_message)
        return {
            "ok": False, 
            "error": f"触发时间 {trigger_time_str} 已经过去（当前时间 {current_time_str}），请设置一个未来的时间",
            "suggestion": "请使用更长的相对时间（如'5分钟后'）或使用绝对时间格式"
        }
    
    # ========== 去重检查 ==========
    existing = reminder_dao.find_similar_reminder(
        user_id=user_id,
        title=title,
        trigger_time=timestamp,
        recurrence_type=recurrence_type,
        time_tolerance=300  # 5分钟容差
    )
    
    if existing:
        existing_id = existing.get("reminder_id", "")
        existing_time = existing.get("next_trigger_time", 0)
        from datetime import datetime
        existing_time_str = datetime.fromtimestamp(existing_time).strftime('%Y年%m月%d日%H时%M分') if existing_time else ""
        
        logger.info(f"Duplicate reminder detected: title={title}, existing_id={existing_id}")
        
        # 语义化输出重复提醒信息
        semantic_message = f"重复提醒：用户已有相同的提醒「{title}」({existing_time_str})，无需重复创建"
        _save_reminder_result_to_session(semantic_message)
        
        return {
            "ok": True,
            "reminder_id": existing_id,
            "duplicate": True,
            "message": f"已存在相同的提醒「{title}」，时间: {existing_time_str}"
        }
    
    # 解析时间段参数
    time_period_config = None
    if period_start and period_end:
        # 解析 period_days
        active_days = None
        if period_days:
            try:
                active_days = [int(d.strip()) for d in period_days.split(",")]
            except:
                logger.warning(f"Failed to parse period_days: {period_days}")
        
        time_period_config = {
            "enabled": True,
            "start_time": period_start,
            "end_time": period_end,
            "active_days": active_days,
            "timezone": "Asia/Shanghai"
        }
        logger.info(f"Time period config: {time_period_config}")
    elif period_start or period_end:
        # 只设置了其中一个参数，记录警告但不影响提醒创建
        logger.warning(f"Incomplete time period config: period_start={period_start}, period_end={period_end}. Ignoring time period.")
    
    # Build reminder document
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
            "interval": recurrence_interval
        },
        "status": "confirmed",
        "created_at": current_time,
        "updated_at": current_time,
        "triggered_count": 0
    }
    
    # Add time period config if present
    if time_period_config:
        reminder_doc["time_period"] = time_period_config
        reminder_doc["period_state"] = {
            "today_first_trigger": None,
            "today_last_trigger": None,
            "today_trigger_count": 0
        }
    
    # Add optional fields
    if conversation_id:
        reminder_doc["conversation_id"] = conversation_id
    if character_id:
        reminder_doc["character_id"] = character_id
    
    # Create reminder
    try:
        inserted_id = reminder_dao.create_reminder(reminder_doc)
        if inserted_id:
            from datetime import datetime
            trigger_time_str = datetime.fromtimestamp(timestamp).strftime('%Y年%m月%d日%H时%M分')
            logger.info(f"Reminder created: id={reminder_id}, title={title}, time={trigger_time_str}")
            
            # 语义化输出创建成功信息
            recurrence_desc = ""
            if recurrence_type != "none":
                recurrence_map = {"daily": "每天", "weekly": "每周", "monthly": "每月", "yearly": "每年", "hourly": "每小时", "interval": f"每{recurrence_interval}分钟"}
                recurrence_desc = f"，周期：{recurrence_map.get(recurrence_type, recurrence_type)}"
            
            # 时间段描述
            period_desc = ""
            if time_period_config:
                days_map = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
                if time_period_config.get("active_days") == [1,2,3,4,5]:
                    days_str = "工作日"
                elif time_period_config.get("active_days"):
                    days_str = "、".join([days_map[d] for d in time_period_config["active_days"]])
                else:
                    days_str = "每天"
                period_desc = f"，时间段：{days_str} {time_period_config['start_time']}-{time_period_config['end_time']}"
            
            semantic_message = f"系统动作(非用户消息)：已按照用户最新的要求创建提醒成功：已为用户设置「{title}」提醒，时间为{trigger_time_str}{recurrence_desc}{period_desc}"
            _save_reminder_result_to_session(semantic_message)
            
            return {
                "ok": True,
                "status": "created",
                "reminder_id": reminder_id,
                "title": title,
                "trigger_time": trigger_time_str,
                "message": f"已创建提醒「{title}」，时间: {trigger_time_str}{recurrence_desc}{period_desc}"
            }
        else:
            _save_reminder_result_to_session("提醒创建失败：数据库写入失败，请稍后重试")
            return {"ok": False, "error": "创建提醒失败"}
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        _save_reminder_result_to_session(f"提醒创建失败：{str(e)}")
        return {"ok": False, "error": str(e)}


def _batch_create_reminders(
    reminder_dao: ReminderDAO,
    user_id: str,
    reminders_json: Optional[str],
    conversation_id: Optional[str],
    character_id: Optional[str],
    base_timestamp: Optional[int] = None
) -> dict:
    """
    批量创建多个提醒，一次调用完成所有创建。
    
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
        _save_reminder_result_to_session(f"批量创建失败：JSON解析错误 - {str(e)}")
        return {"ok": False, "error": f"reminders 参数格式错误: {str(e)}"}
    
    if not reminders_list:
        _save_reminder_result_to_session("批量创建失败：提醒列表为空")
        return {"ok": False, "error": "提醒列表不能为空"}
    
    # 限制批量创建数量，防止滥用
    MAX_BATCH_SIZE = 20
    if len(reminders_list) > MAX_BATCH_SIZE:
        _save_reminder_result_to_session(f"批量创建失败：一次最多创建{MAX_BATCH_SIZE}个提醒，当前请求{len(reminders_list)}个")
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
            failed_reminders.append({
                "index": i,
                "title": title or "(未指定)",
                "error": "缺少 title 或 trigger_time"
            })
            continue
        
        # 解析时间
        is_relative_time = any(keyword in trigger_time for keyword in ['分钟后', '小时后', '天后', '明天', '后天', '下周'])
        if is_relative_time:
            timestamp = _parse_trigger_time(trigger_time, current_time)
        else:
            timestamp = _parse_trigger_time(trigger_time, base_timestamp)
        
        if not timestamp:
            failed_reminders.append({
                "index": i,
                "title": title,
                "error": f"无法解析时间: {trigger_time}"
            })
            continue
        
        # 验证时间在未来
        if timestamp <= current_time:
            trigger_time_str = datetime.fromtimestamp(timestamp).strftime('%Y年%m月%d日%H时%M分')
            failed_reminders.append({
                "index": i,
                "title": title,
                "error": f"时间已过去: {trigger_time_str}"
            })
            continue
        
        # 去重检查
        existing = reminder_dao.find_similar_reminder(
            user_id=user_id,
            title=title,
            trigger_time=timestamp,
            recurrence_type=recurrence_type,
            time_tolerance=300
        )
        
        if existing:
            existing_time = existing.get("next_trigger_time", 0)
            existing_time_str = datetime.fromtimestamp(existing_time).strftime('%Y年%m月%d日%H时%M分') if existing_time else ""
            created_reminders.append({
                "title": title,
                "trigger_time": existing_time_str,
                "status": "duplicate",
                "message": f"已存在相同提醒"
            })
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
                "interval": recurrence_interval
            },
            "status": "confirmed",
            "created_at": current_time,
            "updated_at": current_time,
            "triggered_count": 0
        }
        
        if conversation_id:
            reminder_doc["conversation_id"] = conversation_id
        if character_id:
            reminder_doc["character_id"] = character_id
        
        try:
            inserted_id = reminder_dao.create_reminder(reminder_doc)
            if inserted_id:
                trigger_time_str = datetime.fromtimestamp(timestamp).strftime('%Y年%m月%d日%H时%M分')
                created_reminders.append({
                    "reminder_id": reminder_id,
                    "title": title,
                    "trigger_time": trigger_time_str,
                    "status": "created"
                })
                logger.info(f"Batch created reminder: id={reminder_id}, title={title}, time={trigger_time_str}")
            else:
                failed_reminders.append({
                    "index": i,
                    "title": title,
                    "error": "数据库写入失败"
                })
        except Exception as e:
            failed_reminders.append({
                "index": i,
                "title": title,
                "error": str(e)
            })
    
    # 构建语义化消息
    if created_reminders:
        success_list = [f"「{r['title']}」({r['trigger_time']})" for r in created_reminders if r.get('status') == 'created']
        duplicate_list = [f"「{r['title']}」(已存在)" for r in created_reminders if r.get('status') == 'duplicate']
        
        msg_parts = []
        if success_list:
            msg_parts.append(f"成功创建{len(success_list)}个提醒：{', '.join(success_list)}")
        if duplicate_list:
            msg_parts.append(f"跳过{len(duplicate_list)}个重复提醒：{', '.join(duplicate_list)}")
        if failed_reminders:
            fail_list = [f"「{r['title']}」({r['error']})" for r in failed_reminders]
            msg_parts.append(f"失败{len(failed_reminders)}个：{', '.join(fail_list)}")
        
        semantic_message = f"批量创建提醒结果：{'；'.join(msg_parts)}"
    else:
        semantic_message = f"批量创建失败：所有{len(failed_reminders)}个提醒都未能创建"
    
    _save_reminder_result_to_session(semantic_message)
    
    return {
        "ok": len(created_reminders) > 0,
        "created": created_reminders,
        "failed": failed_reminders,
        "summary": {
            "total": len(reminders_list),
            "created": len([r for r in created_reminders if r.get('status') == 'created']),
            "duplicate": len([r for r in created_reminders if r.get('status') == 'duplicate']),
            "failed": len(failed_reminders)
        },
        "message": semantic_message
    }


def _batch_operations(
    reminder_dao: ReminderDAO,
    user_id: str,
    operations_json: Optional[str],
    conversation_id: Optional[str],
    character_id: Optional[str],
    base_timestamp: Optional[int] = None
) -> dict:
    """
    批量执行多个操作（创建/更新/删除的任意组合）。
    
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
    import json
    from datetime import datetime
    
    if not operations_json:
        _save_reminder_result_to_session("批量操作失败：未提供操作列表")
        return {"ok": False, "error": "批量操作需要提供 operations 参数"}
    
    # 解析 JSON
    try:
        operations_list = json.loads(operations_json)
        if not isinstance(operations_list, list):
            raise ValueError("operations 必须是数组")
    except (json.JSONDecodeError, ValueError) as e:
        _save_reminder_result_to_session(f"批量操作失败：JSON解析错误 - {str(e)}")
        return {"ok": False, "error": f"operations 参数格式错误: {str(e)}"}
    
    if not operations_list:
        _save_reminder_result_to_session("批量操作失败：操作列表为空")
        return {"ok": False, "error": "操作列表不能为空"}
    
    # 限制批量操作数量
    MAX_BATCH_SIZE = 20
    if len(operations_list) > MAX_BATCH_SIZE:
        _save_reminder_result_to_session(f"批量操作失败：一次最多执行{MAX_BATCH_SIZE}个操作")
        return {"ok": False, "error": f"一次最多执行{MAX_BATCH_SIZE}个操作"}
    
    current_time = int(time.time())
    results = []
    success_count = 0
    
    for i, op in enumerate(operations_list):
        op_action = op.get("action")
        op_result = {"index": i, "action": op_action}
        
        if op_action == "create":
            # 创建提醒
            title = op.get("title")
            trigger_time = op.get("trigger_time")
            recurrence_type = op.get("recurrence_type", "none")
            recurrence_interval = op.get("recurrence_interval", 1)
            
            if not title or not trigger_time:
                op_result["ok"] = False
                op_result["error"] = "缺少 title 或 trigger_time"
                results.append(op_result)
                continue
            
            # 解析时间
            is_relative = any(k in trigger_time for k in ['分钟后', '小时后', '天后', '明天', '后天', '下周'])
            timestamp = _parse_trigger_time(trigger_time, current_time if is_relative else base_timestamp)
            
            if not timestamp:
                op_result["ok"] = False
                op_result["error"] = f"无法解析时间: {trigger_time}"
                results.append(op_result)
                continue
            
            if timestamp <= current_time:
                op_result["ok"] = False
                op_result["error"] = "时间已过去"
                results.append(op_result)
                continue
            
            # 去重检查
            existing = reminder_dao.find_similar_reminder(user_id, title, timestamp, recurrence_type, 300)
            if existing:
                op_result["ok"] = True
                op_result["status"] = "duplicate"
                op_result["title"] = title
                results.append(op_result)
                success_count += 1
                continue
            
            # 创建
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
                    "interval": recurrence_interval
                },
                "status": "confirmed",
                "created_at": current_time,
                "updated_at": current_time,
                "triggered_count": 0
            }
            if conversation_id:
                reminder_doc["conversation_id"] = conversation_id
            if character_id:
                reminder_doc["character_id"] = character_id
            
            try:
                if reminder_dao.create_reminder(reminder_doc):
                    trigger_time_str = datetime.fromtimestamp(timestamp).strftime('%Y年%m月%d日%H时%M分')
                    op_result["ok"] = True
                    op_result["status"] = "created"
                    op_result["title"] = title
                    op_result["trigger_time"] = trigger_time_str
                    op_result["reminder_id"] = reminder_id
                    success_count += 1
                else:
                    op_result["ok"] = False
                    op_result["error"] = "数据库写入失败"
            except Exception as e:
                op_result["ok"] = False
                op_result["error"] = str(e)
        
        elif op_action == "update":
            # 更新提醒
            reminder_id = op.get("reminder_id")
            if not reminder_id:
                op_result["ok"] = False
                op_result["error"] = "缺少 reminder_id"
                results.append(op_result)
                continue
            
            existing = reminder_dao.get_reminder_by_id(reminder_id)
            if not existing:
                op_result["ok"] = False
                op_result["error"] = "找不到提醒"
                results.append(op_result)
                continue
            
            update_fields = {}
            if op.get("title"):
                update_fields["title"] = op["title"]
            if op.get("trigger_time"):
                ts = _parse_trigger_time(op["trigger_time"])
                if ts:
                    update_fields["next_trigger_time"] = ts
                    update_fields["time_original"] = op["trigger_time"]
            
            if update_fields:
                try:
                    if reminder_dao.update_reminder(reminder_id, update_fields):
                        op_result["ok"] = True
                        op_result["status"] = "updated"
                        op_result["title"] = existing.get("title")
                        success_count += 1
                    else:
                        op_result["ok"] = False
                        op_result["error"] = "更新失败"
                except Exception as e:
                    op_result["ok"] = False
                    op_result["error"] = str(e)
            else:
                op_result["ok"] = False
                op_result["error"] = "没有要更新的字段"
        
        elif op_action == "delete":
            # 删除提醒
            reminder_id = op.get("reminder_id")
            if not reminder_id:
                op_result["ok"] = False
                op_result["error"] = "缺少 reminder_id"
                results.append(op_result)
                continue
            
            existing = reminder_dao.get_reminder_by_id(reminder_id)
            if not existing:
                op_result["ok"] = False
                op_result["error"] = "找不到提醒"
                results.append(op_result)
                continue
            
            try:
                if reminder_dao.delete_reminder(reminder_id):
                    op_result["ok"] = True
                    op_result["status"] = "deleted"
                    op_result["title"] = existing.get("title")
                    success_count += 1
                else:
                    op_result["ok"] = False
                    op_result["error"] = "删除失败"
            except Exception as e:
                op_result["ok"] = False
                op_result["error"] = str(e)
        
        else:
            op_result["ok"] = False
            op_result["error"] = f"不支持的操作类型: {op_action}"
        
        results.append(op_result)
    
    # 构建语义化消息
    created = [r for r in results if r.get("status") == "created"]
    updated = [r for r in results if r.get("status") == "updated"]
    deleted = [r for r in results if r.get("status") == "deleted"]
    failed = [r for r in results if not r.get("ok")]
    
    msg_parts = []
    if created:
        msg_parts.append(f"创建{len(created)}个提醒")
    if updated:
        msg_parts.append(f"更新{len(updated)}个提醒")
    if deleted:
        msg_parts.append(f"删除{len(deleted)}个提醒")
    if failed:
        msg_parts.append(f"失败{len(failed)}个")
    
    semantic_message = f"批量操作完成：{'，'.join(msg_parts)}" if msg_parts else "批量操作完成"
    _save_reminder_result_to_session(semantic_message)
    
    return {
        "ok": success_count > 0,
        "results": results,
        "summary": {
            "total": len(operations_list),
            "success": success_count,
            "created": len(created),
            "updated": len(updated),
            "deleted": len(deleted),
            "failed": len(failed)
        },
        "message": semantic_message
    }


def _update_reminder(
    reminder_dao: ReminderDAO,
    reminder_id: Optional[str],
    title: Optional[str],
    trigger_time: Optional[str],
    action_template: Optional[str],
    recurrence_type: str,
    recurrence_interval: int
) -> dict:
    """Update an existing reminder."""
    if not reminder_id:
        _save_reminder_result_to_session("提醒修改失败：未指定要修改的提醒ID")
        return {"ok": False, "error": "更新操作需要提供 reminder_id"}
    
    # Check if reminder exists
    existing = reminder_dao.get_reminder_by_id(reminder_id)
    if not existing:
        _save_reminder_result_to_session(f"提醒修改失败：找不到指定的提醒")
        return {"ok": False, "error": f"找不到提醒: {reminder_id}"}
    
    # Build update fields
    update_fields = {}
    update_desc = []
    
    if title:
        update_fields["title"] = title
        update_desc.append(f"标题改为「{title}」")
    
    if trigger_time:
        timestamp = _parse_trigger_time(trigger_time)
        if timestamp:
            update_fields["next_trigger_time"] = timestamp
            update_fields["time_original"] = trigger_time
            from datetime import datetime
            time_str = datetime.fromtimestamp(timestamp).strftime('%Y年%m月%d日%H时%M分')
            update_desc.append(f"时间改为{time_str}")
        else:
            _save_reminder_result_to_session(f"提醒修改失败：无法解析时间「{trigger_time}」")
            return {"ok": False, "error": f"无法解析时间: {trigger_time}"}
    
    if action_template:
        update_fields["action_template"] = action_template
    
    if recurrence_type:
        update_fields["recurrence"] = {
            "enabled": recurrence_type != "none",
            "type": recurrence_type if recurrence_type != "none" else None,
            "interval": recurrence_interval
        }
        if recurrence_type != "none":
            recurrence_map = {"daily": "每天", "weekly": "每周", "monthly": "每月", "yearly": "每年"}
            update_desc.append(f"周期改为{recurrence_map.get(recurrence_type, recurrence_type)}")
    
    if not update_fields:
        _save_reminder_result_to_session("提醒修改失败：未提供要修改的内容")
        return {"ok": False, "error": "没有提供要更新的字段"}
    
    # Update reminder
    try:
        success = reminder_dao.update_reminder(reminder_id, update_fields)
        if success:
            original_title = existing.get("title", "")
            desc_str = "、".join(update_desc) if update_desc else "已更新"
            semantic_message = f"提醒修改成功：「{original_title}」{desc_str}"
            _save_reminder_result_to_session(semantic_message)
        return {"ok": success}
    except Exception as e:
        logger.error(f"Failed to update reminder: {e}")
        _save_reminder_result_to_session(f"提醒修改失败：{str(e)}")
        return {"ok": False, "error": str(e)}


def _delete_reminder(
    reminder_dao: ReminderDAO,
    reminder_id: Optional[str]
) -> dict:
    """Delete a reminder."""
    if not reminder_id:
        _save_reminder_result_to_session("提醒删除失败：未指定要删除的提醒ID")
        return {"ok": False, "error": "删除操作需要提供 reminder_id"}
    
    # Check if reminder exists
    existing = reminder_dao.get_reminder_by_id(reminder_id)
    if not existing:
        _save_reminder_result_to_session("提醒删除失败：找不到指定的提醒")
        return {"ok": False, "error": f"找不到提醒: {reminder_id}"}
    
    title = existing.get("title", "")
    
    # Delete reminder
    try:
        success = reminder_dao.delete_reminder(reminder_id)
        if success:
            semantic_message = f"提醒删除成功：已取消「{title}」的提醒"
            _save_reminder_result_to_session(semantic_message)
        return {"ok": success}
    except Exception as e:
        logger.error(f"Failed to delete reminder: {e}")
        _save_reminder_result_to_session(f"提醒删除失败：{str(e)}")
        return {"ok": False, "error": str(e)}


def _list_reminders(
    reminder_dao: ReminderDAO,
    user_id: str
) -> dict:
    """List all reminders for a user."""
    try:
        reminders = reminder_dao.find_reminders_by_user(user_id)
        
        # Format reminders for output
        formatted_reminders = []
        reminder_summaries = []
        for i, reminder in enumerate(reminders, 1):
            formatted = {
                "reminder_id": reminder.get("reminder_id"),
                "title": reminder.get("title"),
                "status": reminder.get("status"),
                "next_trigger_time": reminder.get("next_trigger_time"),
                "time_friendly": format_time_friendly(reminder.get("next_trigger_time", 0)) if reminder.get("next_trigger_time") else "",
                "recurrence": reminder.get("recurrence", {}),
                "created_at": reminder.get("created_at"),
                "triggered_count": reminder.get("triggered_count", 0)
            }
            formatted_reminders.append(formatted)
            
            # 构建简洁的提醒摘要
            title = reminder.get("title", "")
            time_friendly = formatted["time_friendly"] or "未设置时间"
            reminder_summaries.append(f"{i}.{title}({time_friendly})")
        
        # 语义化输出查询结果
        if formatted_reminders:
            summary_str = " ".join(reminder_summaries)
            semantic_message = f"查询成功：用户当前有{len(formatted_reminders)}个待执行的提醒：{summary_str}"
        else:
            semantic_message = "查询成功：用户当前没有待执行的提醒"
        _save_reminder_result_to_session(semantic_message)
        
        return {"ok": True, "reminders": formatted_reminders}
    except Exception as e:
        logger.error(f"Failed to list reminders: {e}")
        _save_reminder_result_to_session(f"提醒查询失败：{str(e)}")
        return {"ok": False, "error": str(e)}
