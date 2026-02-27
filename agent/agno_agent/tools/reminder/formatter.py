# -*- coding: utf-8 -*-
"""
ReminderFormatter module for reminder tools.

Provides message formatting utilities for reminder operation responses.
Extracted from reminder_tools.py as part of the layered architecture refactor.
"""

import logging
from typing import Any, Optional

from .parser import TimeParser

logger = logging.getLogger(__name__)


class ReminderFormatter:
    """
    Format reminder operation responses and messages.

    This class provides methods to format various reminder operation results
    into user-friendly messages, including:
    - Creation success/failure
    - Update success/failure
    - Deletion success/failure
    - Completion success/failure
    - Filter/query results
    - Batch operation summaries
    - Guard rejection responses
    - Error responses

    Args:
        time_parser: Optional TimeParser instance for time formatting.
                    If None, creates a new instance.
    """

    def __init__(self, time_parser: Optional[TimeParser] = None) -> None:
        """
        Initialize ReminderFormatter with optional TimeParser.

        Args:
            time_parser: Optional TimeParser instance for time formatting.
        """
        self.time_parser = time_parser or TimeParser()

    def create_success(self, reminder: dict[str, Any]) -> str:
        """
        Format creation success response.

        Args:
            reminder: Reminder dictionary with keys:
                - title: Reminder title
                - next_trigger_time: Optional trigger timestamp
                - recurrence: Recurrence configuration

        Returns:
            Formatted success message.
        """
        title = reminder.get("title", "未命名")
        trigger_time = reminder.get("next_trigger_time")
        recurrence = reminder.get("recurrence", {})

        if trigger_time:
            # Format time for display
            trigger_time_str = self.time_parser.format_with_date(trigger_time)
            time_str = f"时间: {trigger_time_str}"

            # Add recurrence description
            recurrence_desc = self._format_recurrence(recurrence)

            # Add period description if applicable
            period_desc = self._format_period(reminder)

            return (
                f"已创建提醒「{title}」，{time_str}" f"{recurrence_desc}{period_desc}"
            )
        else:
            # Inbox task without time
            return f"已创建任务「{title}」（无时间，存入收集箱）"

    def update_success(self, reminder: dict[str, Any], changes: dict[str, Any]) -> str:
        """
        Format update success response.

        Args:
            reminder: Updated reminder dictionary.
            changes: Dictionary of changes made with keys:
                - title: Old title (optional)
                - new_title: New title (optional)
                - trigger_time: New trigger time (optional)
                - recurrence_type: New recurrence type (optional)

        Returns:
            Formatted success message.
        """
        title = reminder.get("title", "")
        old_title = changes.get("title", "")
        new_title = changes.get("new_title", "")

        # Build description of changes
        desc_parts = []
        if new_title and new_title != old_title:
            desc_parts.append(f"标题改为「{new_title}」")

        if changes.get("trigger_time"):
            desc_parts.append(f"时间改为{changes['trigger_time']}")

        if changes.get("recurrence_type"):
            recurrence_type = changes["recurrence_type"]
            recurrence_map = {
                "daily": "每天",
                "weekly": "每周",
                "monthly": "每月",
                "yearly": "每年",
                "interval": f"每{changes.get('recurrence_interval', 1)}分钟",
            }
            desc_parts.append(
                f"周期改为{recurrence_map.get(recurrence_type, recurrence_type)}"
            )

        desc_str = "、".join(desc_parts) if desc_parts else "已更新"

        # Determine which keyword/title to show
        keyword = old_title or new_title or title
        title_str = f"「{keyword}」" if keyword else ""

        return f"提醒修改成功：已更新包含{title_str}的提醒，{desc_str}"

    def delete_success(self, count: int, keyword: str) -> str:
        """
        Format deletion success response.

        Args:
            count: Number of reminders deleted.
            keyword: Keyword used for deletion ("*" for all).

        Returns:
            Formatted success message.
        """
        if keyword == "*":
            if count > 0:
                return f"提醒删除成功：已删除全部 {count} 个待办提醒"
            else:
                return "提醒删除完成：用户当前没有待办提醒"
        else:
            return f"提醒删除成功：已删除包含「{keyword}」的提醒（{count}个）"

    def complete_success(self, count: int, keyword: str) -> str:
        """
        Format completion success response.

        Args:
            count: Number of reminders completed.
            keyword: Keyword used for completion.

        Returns:
            Formatted success message.
        """
        return f"提醒完成成功：已完成包含「{keyword}」的提醒（{count}个）"

    def filter_result(self, reminders: list[dict[str, Any]]) -> str:
        """
        Format filter/query results.

        Args:
            reminders: List of reminder dictionaries.

        Returns:
            Formatted filter results message.
        """
        if not reminders:
            return "当前没有符合条件的提醒"

        # Group reminders: with time vs without time (inbox)
        reminders_with_time = [r for r in reminders if r.get("next_trigger_time")]
        reminders_inbox = [r for r in reminders if not r.get("next_trigger_time")]

        message_parts = []

        if reminders_with_time:
            message_parts.append("📅 定时提醒：")
            for r in reminders_with_time:
                title = r.get("title", "未命名")
                trigger_time = r.get("next_trigger_time")
                time_str = (
                    self.time_parser.format_with_date(trigger_time)
                    if trigger_time
                    else ""
                )
                message_parts.append(f"  • {title} - {time_str}")

        if reminders_inbox:
            message_parts.append("\n📥 待安排：")
            for r in reminders_inbox:
                title = r.get("title", "未命名")
                message_parts.append(f"  • {title}")

        return "\n".join(message_parts)

    def batch_summary(self, results: list[dict[str, Any]]) -> str:
        """
        Format batch operation summary.

        Args:
            results: List of operation result dictionaries.

        Returns:
            Formatted batch summary message.
        """
        # Categorize results
        created = [r for r in results if r.get("status") == "created"]
        appended = [r for r in results if r.get("status") == "appended"]
        duplicate = [r for r in results if r.get("status") == "duplicate"]
        updated = [r for r in results if r.get("status") == "updated"]
        deleted = [r for r in results if r.get("status") == "deleted"]
        completed = [r for r in results if r.get("status") == "completed"]
        already_completed = [
            r for r in results if r.get("status") == "already_completed"
        ]
        failed = [r for r in results if not r.get("ok")]

        msg_parts = []
        if created:
            msg_parts.append(f"创建{len(created)}个提醒")
        if appended:
            msg_parts.append(f"追加{len(appended)}个提醒")
        if duplicate:
            msg_parts.append(f"跳过{len(duplicate)}个重复提醒")
        if updated:
            msg_parts.append(f"更新{len(updated)}个提醒")
        if deleted:
            msg_parts.append(f"删除{len(deleted)}个提醒")
        if completed:
            msg_parts.append(f"完成{len(completed)}个提醒")
        if already_completed:
            msg_parts.append(f"确认{len(already_completed)}个已完成的提醒")
        if failed:
            msg_parts.append(f"失败{len(failed)}个")

        return f"批量操作完成：{'，'.join(msg_parts)}" if msg_parts else "批量操作完成"

    def guarded_response(self, guard: dict[str, Any], action: str = "") -> str:
        """
        Format side-effect guard rejection response.

        Args:
            guard: Guard response dictionary with keys:
                - allowed: bool (should be False)
                - error: Error message
                - reason: Rejection reason code
                - candidates: Optional list of candidate reminders
                - display: Optional display string for candidates
            action: Action type for specific messaging (delete, complete, etc.)

        Returns:
            Formatted guard rejection message.
        """
        error_msg = guard.get("error", "操作未执行")
        display = guard.get("display", "")

        # Action-specific prefix for better clarity
        action_prefix_map = {
            "delete": "提醒删除",
            "complete": "提醒完成",
            "update": "提醒修改",
            "create": "提醒创建",
        }
        prefix = action_prefix_map.get(action, "提醒操作")

        base_msg = f"{prefix}未执行：{error_msg}"
        if display:
            return f"{base_msg}。可选提醒：{display}"
        return base_msg

    def error(self, message: str, **details: Any) -> str:
        """
        Format error response.

        Args:
            message: Error message.
            **details: Optional additional details for logging.

        Returns:
            Formatted error message.
        """
        if details:
            logger.debug(f"Error details: {details}")
        return f"提醒操作失败：{message}"

    def _get_status_indicator(self, status: str) -> str:
        """
        Get status display indicator.

        Args:
            status: Reminder status value.

        Returns:
            Status indicator string.
        """
        status_map = {
            # New status system
            "active": "⏳待执行",
            "triggered": "🔔已触发",
            "completed": "✓已完成",
            # Backward compatible
            "confirmed": "⏳待执行",
            "pending": "⏳待执行",
            "cancelled": "✗已取消",
        }
        return status_map.get(status, status)

    def _format_recurrence(self, recurrence: dict[str, Any]) -> str:
        """
        Format recurrence configuration for display.

        Args:
            recurrence: Recurrence configuration dictionary.

        Returns:
            Formatted recurrence string.
        """
        if not recurrence or not recurrence.get("enabled"):
            return ""

        recurrence_type = recurrence.get("type", "none")
        if recurrence_type == "none":
            return ""

        recurrence_map = {
            "daily": "每天",
            "weekly": "每周",
            "monthly": "每月",
            "yearly": "每年",
        }

        if recurrence_type in recurrence_map:
            return f"，{recurrence_map[recurrence_type]}重复"
        elif recurrence_type == "interval":
            interval = recurrence.get("interval", 1)
            return f"，每{interval}分钟重复"
        return ""

    def _format_period(self, reminder: dict[str, Any]) -> str:
        """
        Format time period configuration for display.

        Args:
            reminder: Reminder dictionary.

        Returns:
            Formatted period string.
        """
        period = reminder.get("time_period", {})
        if not period or not period.get("enabled"):
            return ""

        start_time = period.get("start_time", "")
        end_time = period.get("end_time", "")
        active_days = period.get("active_days")

        parts = []
        if start_time and end_time:
            parts.append(f"{start_time}-{end_time}")

        if active_days:
            weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
            day_str = "、".join([weekday_names[d - 1] for d in active_days])
            parts.append(f"每周{day_str}")

        if parts:
            return f"（{', '.join(parts)}）"
        return ""
