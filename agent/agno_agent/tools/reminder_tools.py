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
"""

import logging
import uuid
import time
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


# 全局变量存储当前 session_state（在调用前设置）
_current_session_state = {}


def set_reminder_session_state(session_state: dict):
    """设置当前会话状态，供 reminder_tool 使用"""
    global _current_session_state
    _current_session_state = session_state or {}


@tool(description="""提醒管理工具，用于创建、更新、删除、查询提醒。
当用户说"提醒我"、"帮我设个提醒"、"别忘了提醒我"等表达提醒意图时，调用此工具创建提醒。

参数说明:
- action: 操作类型，必须是以下字符串之一: "create"(创建)、"update"(更新)、"delete"(删除)、"list"(列表)
- title: 提醒标题，如"开会"、"喝水"、"休息"
- trigger_time: 触发时间，支持以下格式:
  1. 绝对时间格式（推荐）："xxxx年xx月xx日xx时xx分"，如"2025年12月08日15时00分"
  2. 相对时间格式："X分钟后"、"X小时后"、"X天后"、"明天"、"后天"、"下周"
- recurrence_type: 周期类型，字符串，可选值: "none"(默认)、"daily"、"weekly"、"monthly"、"yearly"、"hourly"、"interval"

注意: 不支持"下午3点"、"晚上8点"、"23:00"等格式，必须转换为绝对时间格式"xxxx年xx月xx日xx时xx分"。

示例调用:
- 用户说"明天早上9点提醒我开会" -> action="create", title="开会", trigger_time="2025年12月09日09时00分"
- 用户说"30分钟后提醒我喝水" -> action="create", title="喝水", trigger_time="30分钟后"
- 用户说"下午3点提醒我休息" -> action="create", title="休息", trigger_time="2025年12月08日15时00分"
""")
def reminder_tool(
    action: str,
    title: Optional[str] = None,
    trigger_time: Optional[str] = None,
    action_template: Optional[str] = None,
    reminder_id: Optional[str] = None,
    recurrence_type: str = "none",
    recurrence_interval: int = 1
) -> dict:
    """
    提醒管理统一工具
    
    Args:
        action: 操作类型 - "create"创建、"update"更新、"delete"删除、"list"列表
        title: 提醒标题，如"开会"、"喝水"
        trigger_time: 触发时间，如"30分钟后"、"明天早上9点"
        action_template: 提醒文案模板（可选）
        reminder_id: 提醒ID（update/delete 时必填）
        recurrence_type: 周期类型，默认"none"
        recurrence_interval: 周期间隔数，默认1
    
    Returns:
        操作结果字典
    """
    global _current_session_state
    
    # 修正 LLM 可能传递的嵌套参数格式问题
    if isinstance(action, dict) and 'action' in action:
        action = action['action']
    
    # 手动验证 action 值
    valid_actions = ("create", "update", "delete", "list")
    if action not in valid_actions:
        return {"ok": False, "error": f"不支持的操作类型: {action}，支持的操作: {valid_actions}"}
    
    # 从全局 session_state 获取用户信息
    user_id = str(_current_session_state.get("user", {}).get("_id", ""))
    character_id = str(_current_session_state.get("character", {}).get("_id", ""))
    conversation_id = str(_current_session_state.get("conversation", {}).get("_id", ""))
    
    if not user_id and action in ["create", "list"]:
        logger.warning("reminder_tool: user_id not found in session_state")
        return {"ok": False, "error": "无法获取用户信息，请稍后重试"}
    
    reminder_dao = ReminderDAO()
    
    logger.info(f"reminder_tool called: action={action}, title={title}, trigger_time={trigger_time}, user_id={user_id}")
    
    try:
        # 获取消息的输入时间戳作为相对时间计算的基准
        message_timestamp = _current_session_state.get("input_timestamp")
        
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
                base_timestamp=message_timestamp
            )
            logger.info(f"reminder_tool create result: {result}")
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
    base_timestamp: Optional[int] = None
) -> dict:
    """Create a new reminder."""
    if not title:
        return {"ok": False, "error": "创建提醒需要提供标题 (title)"}
    
    if not trigger_time:
        return {"ok": False, "error": "创建提醒需要提供触发时间 (trigger_time)"}
    
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
        return {"ok": False, "error": f"无法解析时间: {trigger_time}，请使用格式如 '30分钟后' 或 '2025年12月09日15时00分'"}
    
    # Validate timestamp is in the future
    if timestamp <= current_time:
        from datetime import datetime
        trigger_time_str = datetime.fromtimestamp(timestamp).strftime('%Y年%m月%d日%H时%M分')
        current_time_str = datetime.fromtimestamp(current_time).strftime('%H时%M分')
        return {
            "ok": False, 
            "error": f"触发时间 {trigger_time_str} 已经过去（当前时间 {current_time_str}），请设置一个未来的时间",
            "suggestion": "请使用更长的相对时间（如'5分钟后'）或使用绝对时间格式"
        }
    
    # Build reminder document
    reminder_id = str(uuid.uuid4())
    reminder_doc = {
        "user_id": user_id,
        "reminder_id": reminder_id,
        "title": title,
        "action_template": action_template or f"提醒：{title}",
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
    
    # Add optional fields
    if conversation_id:
        reminder_doc["conversation_id"] = conversation_id
    if character_id:
        reminder_doc["character_id"] = character_id
    
    # Create reminder
    try:
        inserted_id = reminder_dao.create_reminder(reminder_doc)
        if inserted_id:
            return {"ok": True, "reminder_id": reminder_id}
        else:
            return {"ok": False, "error": "创建提醒失败"}
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        return {"ok": False, "error": str(e)}


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
        return {"ok": False, "error": "更新操作需要提供 reminder_id"}
    
    # Check if reminder exists
    existing = reminder_dao.get_reminder_by_id(reminder_id)
    if not existing:
        return {"ok": False, "error": f"找不到提醒: {reminder_id}"}
    
    # Build update fields
    update_fields = {}
    
    if title:
        update_fields["title"] = title
    
    if trigger_time:
        timestamp = _parse_trigger_time(trigger_time)
        if timestamp:
            update_fields["next_trigger_time"] = timestamp
            update_fields["time_original"] = trigger_time
        else:
            return {"ok": False, "error": f"无法解析时间: {trigger_time}"}
    
    if action_template:
        update_fields["action_template"] = action_template
    
    if recurrence_type:
        update_fields["recurrence"] = {
            "enabled": recurrence_type != "none",
            "type": recurrence_type if recurrence_type != "none" else None,
            "interval": recurrence_interval
        }
    
    if not update_fields:
        return {"ok": False, "error": "没有提供要更新的字段"}
    
    # Update reminder
    try:
        success = reminder_dao.update_reminder(reminder_id, update_fields)
        return {"ok": success}
    except Exception as e:
        logger.error(f"Failed to update reminder: {e}")
        return {"ok": False, "error": str(e)}


def _delete_reminder(
    reminder_dao: ReminderDAO,
    reminder_id: Optional[str]
) -> dict:
    """Delete a reminder."""
    if not reminder_id:
        return {"ok": False, "error": "删除操作需要提供 reminder_id"}
    
    # Check if reminder exists
    existing = reminder_dao.get_reminder_by_id(reminder_id)
    if not existing:
        return {"ok": False, "error": f"找不到提醒: {reminder_id}"}
    
    # Delete reminder
    try:
        success = reminder_dao.delete_reminder(reminder_id)
        return {"ok": success}
    except Exception as e:
        logger.error(f"Failed to delete reminder: {e}")
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
        for reminder in reminders:
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
        
        return {"ok": True, "reminders": formatted_reminders}
    except Exception as e:
        logger.error(f"Failed to list reminders: {e}")
        return {"ok": False, "error": str(e)}
