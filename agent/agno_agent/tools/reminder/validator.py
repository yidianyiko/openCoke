# -*- coding: utf-8 -*-
"""
ReminderValidator module.

Provides validation rules and side-effect guards for reminder operations.
This is Part 1: Basic Validation covering:
- Required field validation
- Frequency limit validation
- Duplicate reminder detection
- Operation allowed checks (prevents circular calls)
- Side-effect guard for delete/complete operations

Classes:
    ReminderValidator: Main validator class for reminder operations
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from util.log_util import get_logger

if TYPE_CHECKING:
    from dao.reminder_dao import ReminderDAO

logger = get_logger(__name__)


class ReminderValidator:
    """
    Validator for reminder operations.

    Provides validation methods for reminder creation and operations:
    - check_required_fields: Validates required fields are present
    - check_frequency_limit: Enforces recurrence frequency limits
    - check_duplicate: Detects duplicate/similar reminders
    - check_operation_allowed: Prevents circular tool calls

    Class Constants:
        MIN_INTERVAL_INFINITE: Minimum interval (minutes) for infinite recurring
        MIN_INTERVAL_PERIOD: Minimum interval (minutes) for period reminders
        DEFAULT_MAX_TRIGGERS: Default maximum trigger count
        TIME_TOLERANCE: Time tolerance (seconds) for duplicate detection
        DELETE_ALL_WORDS: Keywords indicating delete-all intent
    """

    MIN_INTERVAL_INFINITE = 60
    MIN_INTERVAL_PERIOD = 25
    DEFAULT_MAX_TRIGGERS = 10
    TIME_TOLERANCE = 60
    DELETE_ALL_WORDS = ["全部", "所有", "清空", "都删", "全删"]

    def __init__(self, dao: "ReminderDAO", user_id: str):
        """
        Initialize the validator.

        Args:
            dao: ReminderDAO instance for data access
            user_id: User ID for context-specific validation
        """
        self.dao = dao
        self.user_id = user_id

    def check_required_fields(
        self, title: Optional[str], trigger_time: Optional[str]
    ) -> Optional[dict]:
        """
        Check required fields for reminder creation.

        Args:
            title: Reminder title (required)
            trigger_time: Trigger time string (optional - inbox tasks allowed)

        Returns:
            None if validation passes, error dict if validation fails

        Error dict format:
            {
                "ok": False,
                "error": "Error message describing missing fields"
            }
        """
        # Title is required and must be non-empty after stripping
        if not title or not isinstance(title, str) or not title.strip():
            logger.warning(
                f"Required field validation failed: title missing for user {self.user_id}"
            )
            return {
                "ok": False,
                "error": "提醒内容不能为空，请提供要提醒的事项",
            }

        # Validation passed
        return None

    def check_frequency_limit(
        self,
        recurrence_type: str,
        recurrence_interval: int,
        has_period: bool,
    ) -> Optional[dict]:
        """
        Check recurrence frequency limits to prevent excessive triggers.

        Rules:
        - Non-interval types: Always allowed
        - Interval type with period: Minimum 25 minutes
        - Interval type without period: Minimum 60 minutes

        Args:
            recurrence_type: Type of recurrence (none/daily/weekly/monthly/interval)
            recurrence_interval: Interval value (meaning depends on type)
            has_period: Whether this is a period-based reminder

        Returns:
            None if validation passes, error dict if validation fails

        Error dict format:
            {
                "ok": False,
                "error": "Error message describing frequency limit"
            }
        """
        # Only interval type needs frequency checking
        if recurrence_type != "interval":
            return None

        # Check interval based on whether it has period constraints
        min_interval = (
            self.MIN_INTERVAL_PERIOD if has_period else self.MIN_INTERVAL_INFINITE
        )

        if recurrence_interval < min_interval:
            logger.warning(
                f"Frequency limit exceeded: interval={recurrence_interval}min, "
                f"min_required={min_interval}min, has_period={has_period}, "
                f"user={self.user_id}"
            )

            if has_period:
                error_msg = (
                    f"频率过高：时间段提醒的间隔不能少于{self.MIN_INTERVAL_PERIOD}分钟，"
                    f"当前设置为每{recurrence_interval}分钟。"
                    "这可能导致服务被限制，也不是 Coke 的设计用途。"
                )
            else:
                error_msg = (
                    f"频率过高：不支持每{recurrence_interval}分钟的无限重复提醒。"
                    "这可能导致服务被限制，也不是 Coke 的设计用途。\n"
                    "建议：\n"
                    "1. 使用时间段提醒（如「上午9点到下午6点每30分钟提醒」，最小间隔25分钟）\n"
                    "2. 或使用小时级别以上的周期（如「每小时」「每天」）"
                )

            return {"ok": False, "error": error_msg}

        # Validation passed
        return None

    def check_duplicate(
        self,
        title: str,
        trigger_time: int,
        recurrence_type: Optional[str],
        tolerance: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Check for existing similar reminders to prevent duplicates.

        Args:
            title: Reminder title
            trigger_time: Trigger time as Unix timestamp
            recurrence_type: Recurrence type (or None for one-time)
            tolerance: Time tolerance in seconds (defaults to TIME_TOLERANCE)

        Returns:
            None if no duplicate found, duplicate response dict if found

        Duplicate response format:
            {
                "ok": True,
                "status": "duplicate",
                "existing_id": "ID of existing reminder"
            }
        """
        if tolerance is None:
            tolerance = self.TIME_TOLERANCE

        existing = self.dao.find_similar_reminder(
            user_id=self.user_id,
            title=title,
            trigger_time=trigger_time,
            recurrence_type=recurrence_type,
            time_tolerance=tolerance,
        )

        if existing:
            existing_id = existing.get("reminder_id", "")
            existing_time = existing.get("next_trigger_time", 0)
            # Format time for message
            if existing_time:
                from datetime import datetime

                time_str = datetime.fromtimestamp(existing_time, tz=ZoneInfo("Asia/Shanghai")).strftime(
                    "%Y年%m月%d日%H时%M分"
                )
                message = f"创建提醒成功：已为用户设置「{title}」提醒，时间为{time_str}"
            else:
                message = f"创建提醒成功：已为用户设置「{title}」提醒"

            logger.info(
                f"Duplicate reminder detected: title={title}, "
                f"existing_id={existing_id}, user={self.user_id}"
            )
            return {
                "ok": True,
                "status": "duplicate",
                "existing_id": existing_id,
                "message": message,
            }

        # No duplicate found
        return None

    def check_operation_allowed(
        self, action: str, session_operations: list
    ) -> Optional[dict]:
        """
        Check if an operation is allowed to prevent circular calls.

        Rules:
        - Batch operation must be the only operation
        - Each individual operation (create/update/delete/etc.) can only be called once
        - Batch cannot be mixed with other operations

        Args:
            action: Operation type to check
            session_operations: List of operations already performed in this session

        Returns:
            None if operation is allowed, error dict if not allowed

        Error dict format:
            {
                "ok": False,
                "error": "Error message explaining why operation is not allowed"
            }
        """
        # Batch operation must be the only operation
        if action == "batch":
            if session_operations:
                logger.warning(
                    f"Batch operation rejected: existing operations={session_operations}"
                )
                return {
                    "ok": False,
                    "error": "batch 操作必须是唯一的操作，不能与其他操作混用",
                }
        # Other operations not allowed after batch
        elif "batch" in session_operations:
            logger.warning(
                f"Operation rejected after batch: action={action}, "
                f"existing_operations={session_operations}"
            )
            return {
                "ok": False,
                "error": "已执行 batch 操作，不能再执行其他操作",
            }

        # Check for duplicate operations
        if action in session_operations:
            logger.warning(
                f"Duplicate operation rejected: action={action}, "
                f"existing_operations={session_operations}"
            )
            return {
                "ok": False,
                "error": f"{action} 操作只能执行一次",
            }

        # Operation is allowed
        return None

    def guard_side_effect(
        self,
        action: str,
        keyword: Optional[str],
        session_state: Optional[dict],
    ) -> dict:
        """
        Guard side-effect actions (delete, complete) to prevent unintended operations.

        This method enforces that destructive operations are only performed when the
        user's intent is explicitly clear from their message text.

        Args:
            action: Operation type (delete, complete, create, update, filter, batch)
            keyword: Keyword/identifier for the reminder to operate on
            session_state: Current session state containing user messages

        Returns:
            Dict with keys:
                - allowed (bool): Whether operation should proceed
                - needs_confirmation (bool): Whether user confirmation is required
                - error (str): Error message if not allowed
                - candidates (list): Active reminder candidates for display
                - resolved_keyword (str|None): The matched/resolved keyword
                - reason (str): Reason for the decision
                - display (str): Formatted display of candidates
        """
        # Non-side-effect actions are always allowed
        if action not in ("delete", "complete"):
            return {"allowed": True}

        # Get user text from session
        user_text = self._get_user_text(session_state).strip()
        kw = (keyword or "").strip()

        # Require user text for side-effect operations
        if not user_text:
            logger.warning(
                f"Side-effect guard blocked: missing user text, action={action}, "
                f"user={self.user_id}"
            )
            return {
                "allowed": False,
                "needs_confirmation": True,
                "error": "无法获取用户本轮原文，已阻止执行有副作用的提醒操作",
                "candidates": [],
                "resolved_keyword": None,
                "reason": "missing_user_text",
            }

        # Get active reminders for matching
        active_candidates = self._get_active_candidates()

        # Check for titles in user text (prioritize exact matches to active reminders)
        matched_titles = []
        for reminder in active_candidates:
            title = str(reminder.get("title") or "").strip()
            if title and title in user_text:
                matched_titles.append(title)
        # Remove duplicates while preserving order
        matched_titles = list(dict.fromkeys(matched_titles))

        # Single match in text - safe to proceed
        if len(matched_titles) == 1:
            logger.info(
                f"Side-effect guard allowed: single title match, "
                f"title={matched_titles[0]}, user={self.user_id}"
            )
            return {
                "allowed": True,
                "needs_confirmation": False,
                "error": "",
                "candidates": [],
                "resolved_keyword": matched_titles[0],
                "reason": "matched_active_title_in_user_text",
            }

        # Multiple matches - ambiguous, need clarification
        if len(matched_titles) > 1:
            logger.warning(
                f"Side-effect guard blocked: ambiguous matches, "
                f"matches={matched_titles}, user={self.user_id}"
            )
            candidates, display = self._summarize_candidates(active_candidates, limit=3)
            return {
                "allowed": False,
                "needs_confirmation": True,
                "error": "本轮消息同时命中多个提醒，无法确定要操作哪一个",
                "candidates": candidates,
                "resolved_keyword": None,
                "reason": "ambiguous_title_matches",
                "display": display,
            }

        # Special case: delete-all requires explicit confirmation
        if kw == "*" and action == "delete":
            if self._contains_any(user_text, self.DELETE_ALL_WORDS):
                logger.info(
                    f"Side-effect guard allowed: explicit delete-all, user={self.user_id}"
                )
                return {
                    "allowed": True,
                    "needs_confirmation": False,
                    "error": "",
                    "candidates": [],
                    "resolved_keyword": None,
                    "reason": "explicit_delete_all",
                }
            logger.warning(
                f"Side-effect guard blocked: delete-all not explicit, user={self.user_id}"
            )
            candidates, display = self._summarize_candidates(active_candidates, limit=3)
            return {
                "allowed": False,
                "needs_confirmation": True,
                "error": '删除全部提醒需要用户明确表示"全部/清空/所有"等意图',
                "candidates": candidates,
                "resolved_keyword": None,
                "reason": "delete_all_not_explicit",
                "display": display,
            }

        # Check if provided keyword is in user text
        if kw and kw in user_text:
            logger.info(
                f"Side-effect guard allowed: keyword in text, keyword={kw}, "
                f"user={self.user_id}"
            )
            return {
                "allowed": True,
                "needs_confirmation": False,
                "error": "",
                "candidates": [],
                "resolved_keyword": kw,
                "reason": "keyword_in_user_text",
            }

        # Default: not safe, require confirmation
        logger.warning(
            f"Side-effect guard blocked: keyword not in text, keyword={kw}, "
            f"user={self.user_id}"
        )
        candidates, display = self._summarize_candidates(active_candidates, limit=3)
        return {
            "allowed": False,
            "needs_confirmation": True,
            "error": "用户本轮消息未明确包含要操作的提醒关键字或标题",
            "candidates": candidates,
            "resolved_keyword": None,
            "reason": "keyword_not_in_user_text",
            "display": display,
        }

    def _get_user_text(self, session_state: Optional[dict]) -> str:
        """
        Extract the user's message text from session state.

        Args:
            session_state: Current session state dictionary

        Returns:
            Concatenated text from all input messages
        """
        if session_state is None:
            return ""

        conversation_info = (session_state.get("conversation", {}) or {}).get(
            "conversation_info", {}
        ) or {}
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

    def _get_active_candidates(self) -> list[dict]:
        """
        Get all active and triggered reminders for the current user.

        Returns:
            List of reminder dictionaries with status 'active' or 'triggered'
        """
        try:
            reminders = self.dao.filter_reminders(
                user_id=self.user_id, status_list=["active", "triggered"]
            )
        except Exception:
            logger.exception(f"Failed to get active reminders for user {self.user_id}")
            reminders = []
        if not isinstance(reminders, list):
            return []
        return reminders

    def _summarize_candidates(
        self, reminders: list[dict], limit: int = 3
    ) -> tuple[list[dict], str]:
        """
        Format reminders for candidate display.

        Args:
            reminders: List of reminder dictionaries
            limit: Maximum number of reminders to format

        Returns:
            Tuple of (candidate_dicts, display_string)
        """
        candidates: list[dict] = []
        lines: list[str] = []
        for r in reminders[:limit]:
            title = str(r.get("title") or "").strip()
            ts = r.get("next_trigger_time")
            time_str = ""
            if isinstance(ts, (int, float)) and ts > 0:
                time_str = datetime.fromtimestamp(int(ts), tz=ZoneInfo("Asia/Shanghai")).strftime("%m月%d日%H:%M")
            if title:
                candidates.append(
                    {
                        "title": title,
                        "time": time_str,
                        "reminder_id": r.get("reminder_id"),
                    }
                )
                lines.append(f"「{title}」{('(' + time_str + ')') if time_str else ''}")
        return candidates, "、".join(lines)

    @staticmethod
    def _contains_any(text: str, candidates: list[str]) -> bool:
        """
        Check if text contains any of the candidate strings.

        Args:
            text: Text to search in
            candidates: List of strings to search for

        Returns:
            True if any candidate is found in text, False otherwise
        """
        if not text:
            return False
        for w in candidates:
            if w and w in text:
                return True
        return False
