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
    """设置当前会话状态，供 k 使用"""
    global _current_session_state
    _current_session_state = session_state or {}


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
    global _current_session_state
    _current_session_state["【提醒设置工具消息】"] = message
    logger.info(f"提醒结果已写入 session_state: {message}")


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
                recurrence_map = {"daily": "每天", "weekly": "每周", "monthly": "每月", "yearly": "每年"}
                recurrence_desc = f"，周期：{recurrence_map.get(recurrence_type, recurrence_type)}"
            semantic_message = f"系统动作(非用户消息)：已按照用户最新的要求创建提醒成功：已为用户设置「{title}」提醒，时间为{trigger_time_str}{recurrence_desc}"
            _save_reminder_result_to_session(semantic_message)
            
            return {
                "ok": True,
                "status": "created",
                "reminder_id": reminder_id,
                "title": title,
                "trigger_time": trigger_time_str,
                "message": f"已创建提醒「{title}」，时间: {trigger_time_str}"
            }
        else:
            _save_reminder_result_to_session("提醒创建失败：数据库写入失败，请稍后重试")
            return {"ok": False, "error": "创建提醒失败"}
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        _save_reminder_result_to_session(f"提醒创建失败：{str(e)}")
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
