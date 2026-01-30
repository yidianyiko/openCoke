# -*- coding: utf-8 -*-
"""
ReminderValidator module.

Provides validation rules and side-effect guards for reminder operations.
This is Part 1: Basic Validation covering:
- Required field validation
- Frequency limit validation
- Duplicate reminder detection
- Operation allowed checks (prevents circular calls)

Classes:
    ReminderValidator: Main validator class for reminder operations
"""

from typing import TYPE_CHECKING, Optional

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
            logger.info(
                f"Duplicate reminder detected: title={title}, "
                f"existing_id={existing_id}, user={self.user_id}"
            )
            return {
                "ok": True,
                "status": "duplicate",
                "existing_id": existing_id,
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
