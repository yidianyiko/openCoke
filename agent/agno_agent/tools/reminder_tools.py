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
from typing import Optional, Literal
from agno.tools import tool

from dao.reminder_dao import ReminderDAO
from util.time_util import parse_relative_time, str2timestamp, format_time_friendly

logger = logging.getLogger(__name__)


def _parse_trigger_time(trigger_time: str) -> Optional[int]:
    """
    Parse trigger time from string to timestamp.
    
    Supports:
    - Relative time: "30分钟后", "2小时后", "明天", "后天", "下周"
    - Absolute time: "2024年12月25日09时00分"
    
    Args:
        trigger_time: Time string to parse
        
    Returns:
        Unix timestamp or None if parsing fails
    """
    if not trigger_time:
        return None
    
    # Try relative time first
    timestamp = parse_relative_time(trigger_time)
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

创建提醒时必须提供:
- action: "create"
- title: 提醒标题，如"开会"、"喝水"、"休息"
- trigger_time: 触发时间，支持以下格式:
  1. 绝对时间格式（推荐）："xxxx年xx月xx日xx时xx分"，如"2025年12月08日15时00分"
  2. 相对时间格式："X分钟后"、"X小时后"、"X天后"、"明天"、"后天"、"下周"

注意: 不支持"下午3点"、"晚上8点"、"23:00"等格式，必须转换为绝对时间格式"xxxx年xx月xx日xx时xx分"。

示例调用:
- 用户说"明天早上9点提醒我开会" -> action="create", title="开会", trigger_time="2025年12月09日09时00分"
- 用户说"30分钟后提醒我喝水" -> action="create", title="喝水", trigger_time="30分钟后"
- 用户说"下午3点提醒我休息" -> action="create", title="休息", trigger_time="2025年12月08日15时00分"
""")
def reminder_tool(
    action: Literal["create", "update", "delete", "list"],
    title: Optional[str] = None,
    trigger_time: Optional[str] = None,
    action_template: Optional[str] = None,
    reminder_id: Optional[str] = None,
    recurrence_type: Literal["none", "daily", "weekly", "monthly", "yearly", "hourly", "interval"] = "none",
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
                character_id=character_id
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
    character_id: Optional[str]
) -> dict:
    """Create a new reminder."""
    if not title:
        return {"ok": False, "error": "创建提醒需要提供标题 (title)"}
    
    if not trigger_time:
        return {"ok": False, "error": "创建提醒需要提供触发时间 (trigger_time)"}
    
    # Parse trigger time
    timestamp = _parse_trigger_time(trigger_time)
    if not timestamp:
        return {"ok": False, "error": f"无法解析时间: {trigger_time}"}
    
    # Validate timestamp is in the future
    current_time = int(time.time())
    if timestamp <= current_time:
        return {"ok": False, "error": "触发时间必须是未来的时间"}
    
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
